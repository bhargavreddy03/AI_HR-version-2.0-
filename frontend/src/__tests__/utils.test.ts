import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn utility function", () => {
  it("merges standard class names correctly", () => {
    const result = cn("px-4", "py-2", "text-sm");
    expect(result).toBe("px-4 py-2 text-sm");
  });

  it("handles conditional classes and filters out falsy values", () => {
    const isActive = true;
    const isDisabled = false;
    const result = cn(
      "base-btn",
      isActive && "bg-blue-600",
      isDisabled && "opacity-50",
      null,
      undefined,
      false,
      ""
    );
    expect(result).toBe("base-btn bg-blue-600");
  });

  it("resolves conflicting Tailwind utility classes deterministically", () => {
    // tailwind-merge resolves later classes over earlier conflicting ones
    const result = cn("p-4 text-red-500", "p-2 text-blue-500");
    expect(result).toBe("p-2 text-blue-500");
  });

  it("handles empty input gracefully", () => {
    expect(cn()).toBe("");
  });
});
