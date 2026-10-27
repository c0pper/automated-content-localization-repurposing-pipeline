import { vi } from "vitest";

// Mock fetch globally for all frontend tests
global.fetch = vi.fn();

// Mock crypto.randomUUID
Object.defineProperty(globalThis, "crypto", {
  value: { randomUUID: () => "test-uuid-1234" },
  writable: true,
});