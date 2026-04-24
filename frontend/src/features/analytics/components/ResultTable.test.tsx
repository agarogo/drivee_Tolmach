/** @vitest-environment jsdom */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResultTable } from "./ResultTable";

const exportRowsToCsvMock = vi.fn();

vi.mock("../lib/exports", () => ({
  exportRowsToCsv: (...args: unknown[]) => exportRowsToCsvMock(...args),
}));

afterEach(() => {
  cleanup();
});

describe("ResultTable", () => {
  it("supports sorting, pagination, and column visibility", async () => {
    const user = userEvent.setup();

    render(
      <ResultTable
        rows={[
          { city: "Tokyo", revenue: 200 },
          { city: "Berlin", revenue: 120 },
          { city: "Paris", revenue: 300 },
        ]}
        columns={[
          { key: "city", label: "City", data_type: "string" },
          { key: "revenue", label: "Revenue", data_type: "number" },
        ]}
        initialPageSize={2}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Revenue/i }));
    const sortedRows = screen.getAllByRole("row");
    expect(sortedRows[1].textContent).toContain("Berlin");

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Paris")).toBeTruthy();

    await user.click(screen.getByText("Columns"));
    await user.click(screen.getByLabelText("Revenue"));
    expect(screen.queryByRole("button", { name: /Revenue/i })).toBeNull();
  });

  it("exports the currently visible table snapshot", async () => {
    const user = userEvent.setup();

    render(
      <ResultTable
        rows={[
          { city: "Tokyo", revenue: 200 },
          { city: "Berlin", revenue: 120 },
        ]}
        columns={[
          { key: "city", label: "City", data_type: "string" },
          { key: "revenue", label: "Revenue", data_type: "number" },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(exportRowsToCsvMock).toHaveBeenCalledTimes(1);
  });
});
