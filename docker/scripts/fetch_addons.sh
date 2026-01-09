#!/bin/sh
set -eu

log() {
	printf '%s\n' "$*"
}

mkdir -p /addons /extra_addons

addons_repos="${ODOO_ADDON_REPOSITORIES:-}"
openupgrade_repo="OCA/OpenUpgrade@${ODOO_VERSION:-19.0}"
case ",${addons_repos}," in
*,OCA/OpenUpgrade@*,* | *,OCA/OpenUpgrade,*) ;;
"",,)
	addons_repos="${openupgrade_repo}"
	;;
*)
	addons_repos="${addons_repos},${openupgrade_repo}"
	;;
esac

link_modules() {
	repo_root="$1"
	root_dir="$2"
	if [ -f "${repo_root}/__manifest__.py" ] || [ -f "${repo_root}/__openerp__.py" ]; then
		return
	fi
	scan_roots=""
	if [ -d "${repo_root}/enterprise" ]; then
		scan_roots="${scan_roots} ${repo_root}/enterprise"
	fi
	if [ -d "${repo_root}/addons" ]; then
		scan_roots="${scan_roots} ${repo_root}/addons"
	fi
	if [ -d "${repo_root}/odoo/addons" ]; then
		scan_roots="${scan_roots} ${repo_root}/odoo/addons"
	fi
	if [ -z "$scan_roots" ]; then
		scan_roots="${repo_root}"
	fi
	for scan_root in ${scan_roots}; do
		for module_dir in "${scan_root}"/*; do
			[ -d "$module_dir" ] || continue
			if [ ! -f "${module_dir}/__manifest__.py" ] && [ ! -f "${module_dir}/__openerp__.py" ]; then
				continue
			fi
			module_name="$(basename "$module_dir")"
			link_path="${root_dir}/${module_name}"
			if [ -e "$link_path" ]; then
				if [ "$(readlink "$link_path" 2>/dev/null)" != "$module_dir" ]; then
					echo "Module ${module_name} already exists in ${root_dir}; skipping link." >&2
				fi
				continue
			fi
			relative_target="$module_dir"
			case "$module_dir" in
			"${root_dir}"/*)
				relative_target="${module_dir#"$root_dir"/}"
				;;
			esac
			ln -s "$relative_target" "$link_path"
		done
	done
}

if [ -n "$addons_repos" ]; then
	if [ -z "${GITHUB_TOKEN:-}" ]; then
		echo "GITHUB_TOKEN missing; cannot clone addons." >&2
		exit 1
	fi
	log "Cloning addon repositories: ${addons_repos}"
	old_ifs="$IFS"
	IFS=','
	for raw in ${addons_repos}; do
		repo="$(echo "$raw" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
		if [ -z "$repo" ]; then
			continue
		fi
		branch="main"
		case "$repo" in
		*@*)
			branch="${repo##*@}"
			repo="${repo%@*}"
			;;
		esac
		name="${repo##*/}"
		remote_url="https://${GITHUB_TOKEN}@github.com/${repo}"
		target_root="/extra_addons"
		log "Cloning addon from ${repo} branch ${branch} into ${target_root}/${name}"
		if ! git clone --branch "$branch" --single-branch --depth 1 \
			"$remote_url" "${target_root}/${name}"; then
			echo "Failed to clone addon repo ${repo} (branch ${branch})." >&2
			exit 1
		fi
		rm -rf "${target_root}/${name}/.git"
		link_modules "${target_root}/${name}" "$target_root"
	done
	IFS="$old_ifs"
else
	log "ODOO_ADDON_REPOSITORIES is empty; skipping clone."
fi
