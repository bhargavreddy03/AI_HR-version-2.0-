import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import HomePage from "@/app/page";

describe("HomePage Component", () => {
  it("renders platform heading and architecture overview", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("heading", { level: 1, name: /AI HR Intelligence Platform/i })
    ).toBeInTheDocument();

    expect(screen.getByText(/Frontend Core:/i)).toBeInTheDocument();
    expect(screen.getByText(/Backend API:/i)).toBeInTheDocument();
    expect(screen.getByText(/Task Processing:/i)).toBeInTheDocument();
    expect(screen.getByText(/Database & Vector:/i)).toBeInTheDocument();
  });
});
