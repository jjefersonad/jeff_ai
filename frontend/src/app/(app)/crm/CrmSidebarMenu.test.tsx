import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CrmSidebarMenu } from "./CrmSidebarMenu";

describe("CrmSidebarMenu (crm-lateral-menu-task-menu-1 unit-1 / REQ-002)", () => {
  it("WHEN rendered THEN it lists Contatos, Empresas, Funil in order", () => {
    render(<CrmSidebarMenu active="contacts" onSelect={vi.fn()} />);

    const entries = screen.getAllByRole("button");
    expect(entries.map((entry) => entry.textContent)).toEqual([
      "Contatos",
      "Empresas",
      "Funil",
    ]);
  });
});

describe("CrmSidebarMenu (crm-lateral-menu-task-menu-1 unit-2 / REQ-002)", () => {
  it("WHEN active='pipeline' THEN only the Funil entry is marked active", () => {
    render(<CrmSidebarMenu active="pipeline" onSelect={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Funil" })).toHaveAttribute(
      "aria-current",
      "true"
    );
    expect(
      screen.getByRole("button", { name: "Contatos" })
    ).not.toHaveAttribute("aria-current");
    expect(
      screen.getByRole("button", { name: "Empresas" })
    ).not.toHaveAttribute("aria-current");
  });
});

describe("CrmSidebarMenu (crm-lateral-menu-task-menu-1 unit-3 / REQ-002)", () => {
  it("WHEN the Empresas entry is clicked THEN onSelect is called with 'companies'", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<CrmSidebarMenu active="contacts" onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: "Empresas" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("companies");
  });
});
