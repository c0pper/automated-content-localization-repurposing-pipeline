import "@testing-library/jest-dom";

// Mock window.location for hash-based routing
Object.defineProperty(window, "location", {
  value: {
    href: "http://localhost:3000/",
    hash: "",
    origin: "http://localhost:3000",
    pathname: "/",
    search: "",
    assign: jest.fn(),
    replace: jest.fn(),
    reload: jest.fn(),
  },
  writable: true,
});

// Mock crypto.randomUUID if available
if (!crypto.randomUUID) {
  crypto.randomUUID = () => `test-${Math.random().toString(36).slice(2)}`;
}