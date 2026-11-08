import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import HomePage from "@/app/page";

describe("HomePage Component", () => {
  it("renders platform heading and architecture overview", () => {
    render(<HomePage />);

    const heading = screen.getByRole("heading", { level: 1, name: /AI HR Intelligence Platform/i });
    expect(heading).toBeDefined();

    expect(screen.getByText(/Frontend Core:/i)).toBeDefined();
    expect(screen.getByText(/Backend API:/i)).toBeDefined();
    expect(screen.getByText(/Task Processing:/i)).toBeDefined();
    expect(screen.getByText(/Database & Vector:/i)).toBeDefined();
  });
});
