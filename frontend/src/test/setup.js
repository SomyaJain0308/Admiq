import "@testing-library/jest-dom/vitest"

// jsdom doesn't implement ResizeObserver, but several Radix UI primitives
// used across the app (Checkbox, Select, ...) call it unconditionally on
// mount. Without this, any test that renders one of those crashes with
// "ResizeObserver is not defined" - this is a real environment gap, not
// something worth stubbing per-test.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
global.ResizeObserver = ResizeObserverStub
