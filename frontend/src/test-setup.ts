import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";
// jsdom has no layout/scroll implementation; browser behavior is covered by E2E.
Object.defineProperty(window, "scrollTo", { value: vi.fn(), writable: true });
