import argparse
import json
import os
import re
from pathlib import Path

import requests
from ariadne_codegen.main import client as codegen_client
from graphql import IntrospectionQuery, build_client_schema, get_introspection_query, print_schema

from tools.platform import environment as platform_environment

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ADDONS_PATH = REPOSITORY_ROOT / "addons" / "shopify_sync"
GRAPHQL_PATH = ADDONS_PATH / "graphql"
GRAPHQL_ENV_FILE_NAMES = (".env", ".env.local")
DEFAULT_CONTEXT_NAME = "opw"
DEFAULT_INSTANCE_NAME = "local"


def load_runtime_env_values(
    *,
    repository_root: Path,
    env_file: Path | None,
    context_name: str,
    instance_name: str,
) -> dict[str, str]:
    env_file_candidates = [
        repository_root / ".env",
        repository_root / "platform" / ".env",
    ]
    if env_file is None:
        for candidate_env_file in env_file_candidates:
            if candidate_env_file.exists():
                env_file = candidate_env_file
                break
    if env_file is None:
        return platform_environment.load_secret_environment(
            repository_root,
            context_name=context_name,
            instance_name=instance_name,
        )

    _env_file_path, environment_values = platform_environment.load_environment(
        repository_root,
        env_file,
        context_name=context_name,
        instance_name=instance_name,
    )
    return environment_values


def parse_arguments() -> argparse.Namespace:
    argument_parser = argparse.ArgumentParser(description="Fetch Shopify GraphQL schema and regenerate generated models.")
    argument_parser.add_argument("--context", default=DEFAULT_CONTEXT_NAME)
    argument_parser.add_argument("--instance", default=DEFAULT_INSTANCE_NAME)
    argument_parser.add_argument("--env-file", type=Path, default=None)
    return argument_parser.parse_args()


def resolve_runtime_env_value(environment_values: dict[str, str], variable_name: str) -> str | None:
    process_value = os.getenv(variable_name)
    if process_value is not None and process_value.strip():
        return process_value
    file_value = environment_values.get(variable_name)
    if file_value is not None and file_value.strip():
        return file_value
    return None


def fetch_shopify_introspection(endpoint: str, token: str) -> dict[str, dict[str, str]]:
    introspection_query = get_introspection_query()
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": token,
    }
    print(f"Fetching introspection schema from {endpoint}...")
    response = requests.post(endpoint, json={"query": introspection_query}, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Error fetching schema: {response.status_code} {response.text}")
    result = response.json()
    if "data" not in result:
        raise Exception(f"Invalid introspection result: {result}")
    return result["data"]


def save_introspection_json(data: dict[str, dict[str, str]], file_path: Path) -> None:
    file_path.write_text(json.dumps(data, indent=2))
    print(f"Saved introspection JSON schema to {file_path}")


def save_schema_sdl(json_data: IntrospectionQuery, output_file_path: Path) -> None:
    schema = build_client_schema(json_data)
    sdl = print_schema(schema)
    sdl = re.sub(r'""".*?"""', '""', sdl, flags=re.DOTALL)
    output_file_path.write_text(sdl)


def resolve_graphql_env_file(graphql_path: Path) -> Path | None:
    for env_file_name in GRAPHQL_ENV_FILE_NAMES:
        env_file_path = graphql_path / env_file_name
        if env_file_path.exists():
            return env_file_path
    return None


def sync_graphql_ide_api_version(*, graphql_path: Path, shopify_api_version: str) -> None:
    env_file_path = resolve_graphql_env_file(graphql_path)
    if env_file_path is None:
        return

    env_lines = env_file_path.read_text(encoding="utf-8").splitlines()
    api_version_key = "SHOPIFY_GRAPHQL_API_VERSION"
    synchronized_lines: list[str] = []
    did_update_existing_value = False

    for env_line in env_lines:
        if env_line.startswith(f"{api_version_key}="):
            synchronized_lines.append(f"{api_version_key}={shopify_api_version}")
            did_update_existing_value = True
            continue
        synchronized_lines.append(env_line)

    if not did_update_existing_value:
        synchronized_lines.append(f"{api_version_key}={shopify_api_version}")

    env_file_path.write_text("\n".join(synchronized_lines) + "\n", encoding="utf-8")
    print(f"Synchronized Shopify GraphQL IDE API version in {env_file_path}")


def main() -> None:
    parsed_arguments = parse_arguments()
    runtime_env_values = load_runtime_env_values(
        repository_root=REPOSITORY_ROOT,
        env_file=parsed_arguments.env_file,
        context_name=parsed_arguments.context,
        instance_name=parsed_arguments.instance,
    )
    shopify_store_key = resolve_runtime_env_value(runtime_env_values, "ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY")
    shopify_api_token = resolve_runtime_env_value(runtime_env_values, "ENV_OVERRIDE_SHOPIFY__API_TOKEN")
    shopify_api_version = resolve_runtime_env_value(runtime_env_values, "ENV_OVERRIDE_SHOPIFY__API_VERSION")
    missing_vars: list[str] = []
    if not shopify_store_key:
        missing_vars.append("ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY")
    if not shopify_api_token:
        missing_vars.append("ENV_OVERRIDE_SHOPIFY__API_TOKEN")
    if not shopify_api_version:
        missing_vars.append("ENV_OVERRIDE_SHOPIFY__API_VERSION")
    if missing_vars:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")
    assert shopify_store_key is not None
    assert shopify_api_token is not None
    assert shopify_api_version is not None

    addon_path = Path(ADDONS_PATH)
    queries_path = addon_path / "graphql" / "shopify"
    schema_path = addon_path / "graphql" / "schema"
    schema_path.mkdir(parents=True, exist_ok=True)
    introspection_file_path = schema_path / f"shopify_schema_{shopify_api_version}.json"
    sdl_file_path = schema_path / f"shopify_schema_{shopify_api_version}.sdl"
    services_path = addon_path / "services" / "shopify"
    client_name = "gql"

    endpoint = f"https://{shopify_store_key}.myshopify.com/admin/api/{shopify_api_version}/graphql.json"
    print(f"Using Shopify endpoint: {endpoint}")

    if not introspection_file_path.exists():
        introspection_data = fetch_shopify_introspection(endpoint, shopify_api_token)
        save_introspection_json(introspection_data, introspection_file_path)
    else:
        introspection_data = json.loads(introspection_file_path.read_text())

    if not sdl_file_path.exists():
        save_schema_sdl(introspection_data, sdl_file_path)

    sync_graphql_ide_api_version(graphql_path=GRAPHQL_PATH, shopify_api_version=shopify_api_version)

    config_dict = {
        "schema_path": str(sdl_file_path),
        "queries_path": str(queries_path),
        "target_package_name": client_name,
        "target_package_path": str(services_path),
        "convert_to_snake_case": True,
        "async_client": False,
        "plugins": [
            "ariadne_codegen.contrib.shorter_results.ShorterResultsPlugin",
            "ariadne_codegen.contrib.extract_operations.ExtractOperationsPlugin",
        ],
        "scalars": {
            "DateTime": {
                "type": "datetime.datetime",
                "parse": "..helpers.parse_shopify_datetime_to_utc",
                "serialize": "..helpers.format_datetime_for_shopify",
            },
            "Date": {"type": "datetime.date"},
            "Money": {"type": "decimal.Decimal"},
            "Decimal": {"type": "decimal.Decimal"},
            "UnsignedInt64": {"type": "int"},
            "BigInt": {"type": "int"},
            "JSON": {"type": "str"},
            "URL": {"type": "pydantic.AnyUrl"},
            "HTML": {"type": "str"},
            "Color": {"type": "str"},
            "ARN": {"type": "str"},
            "UtcOffset": {"type": "datetime.timedelta"},
            "FormattedString": {"type": "str"},
        },
    }
    codegen_client({"tool": {"ariadne-codegen": config_dict}})

    print("\nGeneration complete.")
    print("You should now have a generated client package (e.g., 'shopify_client')")
    print("in the directory specified by 'target_package_path' as defined in the generated configuration.")


if __name__ == "__main__":
    main()
