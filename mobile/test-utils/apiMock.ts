/** Stand-in for @/services/api: every endpoint is a jest.fn() the tests script per case. */
export const apiMock = {
  api: {},
  authApi: {
    register: jest.fn(),
    login: jest.fn(),
    me: jest.fn(),
    changePassword: jest.fn(),
    deleteAccount: jest.fn(),
  },
  plaidApi: {
    getLinkToken: jest.fn(),
    exchange: jest.fn(),
    sync: jest.fn(),
    items: jest.fn(),
    disconnect: jest.fn(),
    reconnectLinkToken: jest.fn(),
    reconnected: jest.fn(),
  },
  subscriptionsApi: { list: jest.fn(), dismiss: jest.fn(), restore: jest.fn() },
  insightsApi: { get: jest.fn(), generate: jest.fn() },
};

export function resetApiMock() {
  for (const group of Object.values(apiMock)) {
    for (const fn of Object.values(group)) (fn as jest.Mock).mockReset();
  }
}

/** An axios-style failure carrying the API's error body. */
export const apiError = (status: number, detail: unknown) => ({ response: { status, data: { detail } }, message: `HTTP ${status}` });
