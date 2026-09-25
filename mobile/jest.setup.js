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

// TouchableOpacity's press animation finishes after a test's last await; that warning is noise.
const realConsoleError = console.error;
jest.spyOn(console, "error").mockImplementation((...args) => {
  if (typeof args[0] === "string" && args[0].includes("not wrapped in act") && args.join(" ").includes("Animated(")) return;
  realConsoleError(...args);
});

// Icon fonts can't load under Jest (expo-font); icons carry no behaviour worth testing.
jest.mock("@expo/vector-icons", () => ({ Ionicons: () => null }));
