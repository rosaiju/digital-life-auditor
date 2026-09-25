// Native modules that have no JS implementation under Jest.
jest.mock("expo-secure-store", () => {
  const store = new Map();
  return {
    getItemAsync: jest.fn(async (key) => (store.has(key) ? store.get(key) : null)),
    setItemAsync: jest.fn(async (key, value) => void store.set(key, value)),
    deleteItemAsync: jest.fn(async (key) => void store.delete(key)),
  };
});

jest.mock("react-native-safe-area-context", () => require("react-native-safe-area-context/jest/mock").default);

// The real router needs a navigation container; screens only use these few hooks.
jest.mock("expo-router", () => {
  const router = { push: jest.fn(), replace: jest.fn(), back: jest.fn() };
  return {
    __router: router,
    useRouter: () => router,
    useLocalSearchParams: jest.fn(() => ({})),
    useSegments: jest.fn(() => []),
    Link: ({ children }) => children,
    Stack: () => null,
    Tabs: () => null,
  };
});

// Icon fonts can't load under Jest (expo-font); icons carry no behaviour worth testing.
jest.mock("@expo/vector-icons", () => ({ Ionicons: () => null }));

// Make Animated.timing finish immediately so press-feedback animations update inside the press's act()
// instead of ticking on timers after the test has moved on. Layout and behaviour are unaffected.
const { Animated } = require("react-native");
jest.spyOn(Animated, "timing").mockImplementation((value, config) => ({
  start: (callback) => {
    value.setValue(config.toValue);
    callback?.({ finished: true });
  },
  stop: () => {},
  reset: () => {},
}));

// VirtualizedList (FlatList) batches its render-window updates on a timer, which fires outside act().
// Run the batcher synchronously so those updates happen inside the render/event that caused them.
jest.mock("@react-native/virtualized-lists/Interaction/Batchinator", () =>
  class Batchinator {
    constructor(callback) {
      this.callback = callback;
    }
    schedule() {
      this.callback();
    }
    flushIfScheduled() {}
    dispose() {}
  }
);
