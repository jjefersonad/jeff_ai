import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { getConfig, saveConfig, DEFAULT_ASSISTANT_ID } from "./config";

describe("StandaloneConfig profileId (ui-2 / REQ-002)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("saveConfig persists profileId without replacing assistantId with the profile UUID", () => {
    saveConfig({
      assistantId: DEFAULT_ASSISTANT_ID,
      profileId: "profile-marketing",
    });

    expect(getConfig()).toEqual({
      assistantId: DEFAULT_ASSISTANT_ID,
      profileId: "profile-marketing",
    });
  });

  it("getConfig returns a config without profileId when it was never saved", () => {
    saveConfig({ assistantId: DEFAULT_ASSISTANT_ID });

    const config = getConfig();
    expect(config?.assistantId).toBe(DEFAULT_ASSISTANT_ID);
    expect(config?.profileId).toBeUndefined();
  });

  it("saveConfig omits profileId when clearing back to the default agent", () => {
    saveConfig({
      assistantId: DEFAULT_ASSISTANT_ID,
      profileId: "profile-marketing",
    });
    saveConfig({ assistantId: DEFAULT_ASSISTANT_ID, profileId: "" });

    const config = getConfig();
    expect(config).toEqual({ assistantId: DEFAULT_ASSISTANT_ID });
    expect(config?.profileId).toBeUndefined();
  });
});
