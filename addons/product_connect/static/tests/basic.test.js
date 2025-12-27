/** @odoo-module */
 

import { describe, test, expect } from "@odoo/hoot";

describe("@product_connect Basic Product Connect Tests", () => {
    test("should pass basic test", async () => {
        expect(true).toBe(true);
        expect(1 + 1).toBe(2);
    });

    test("should handle arrays", async () => {
        const arr = [1, 2, 3];
        expect(arr).toHaveLength(3);
        // noinspection JSCheckFunctionSignatures Hoot framework type definition issue with number arrays
        expect(arr).toInclude(2);
    });

    test("should handle objects", async () => {
        const obj = { name: "Motor", hp: 100 };
        expect(obj.name).toBe("Motor");
        expect(obj.hp).toBe(100);
    });
});
