import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * saas-empresario-br-task-guard-1 / empresario-ux-pt-br REQ-006:
 * o catálogo de assistentes não ganha modo empresário, rota de
 * onboarding nem subagente de onboarding.
 */
const MODO_PROIBIDO = /empres[aá]rio|onboarding/i;

describe("AssistantModal — saas-empresario-br-task-guard-1 unit-1 / REQ-006", () => {
  it("AssistantModal não declara um catálogo estático de modo empresário", () => {
    const source = readFileSync(
      path.resolve(__dirname, "./AssistantModal.tsx"),
      "utf8"
    );
    expect(source).not.toMatch(MODO_PROIBIDO);
  });

  it("AssistantButton não ganha um modo ou id empresário", () => {
    const source = readFileSync(
      path.resolve(__dirname, "./AssistantButton.tsx"),
      "utf8"
    );
    expect(source).not.toMatch(MODO_PROIBIDO);
  });

  it("não há rota /onboarding no app", () => {
    const appRoot = path.resolve(__dirname, "..");
    expect(existsSync(path.join(appRoot, "onboarding"))).toBe(false);
    expect(existsSync(path.join(appRoot, "(app)", "onboarding"))).toBe(false);
    expect(existsSync(path.join(appRoot, "public", "onboarding"))).toBe(false);
  });
});
