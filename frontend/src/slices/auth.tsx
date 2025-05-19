import {apiSlice} from "../frugalit/slices/api"

export interface LoginConfiguration {
  openId: string
}

export interface UserProfile {
  name: string,
  permissions: string[],
  username: string,
  email: string
}

export interface Credentials {
  username: string,
  password: string
}

const extendedApi = apiSlice.injectEndpoints({
  endpoints: (build => (
    {
      getLoginConfiguration: build.query<LoginConfiguration, { redirectUrl: string }>({
        query: arg => `/login/configuration${arg.redirectUrl ? `?redirectUrl=${encodeURIComponent(arg.redirectUrl)}` : ""}`
      }),
      getProfile: build.mutation<UserProfile, void>({
        query: _ => `/login/profile`,
      }),
      loginOAuth: build.mutation<void, { code: string, redirectUrl: string }>({
        query: arg => ({url: `/login/oauth`, method: "post", body: arg}),
      }),
      loginCredentials: build.mutation<void, Credentials>({
        query: arg => ({url: `/login/credentials`, method: "post", body: arg}),
      }),
      logout: build.mutation<void, void>({
        query: _ => ({url: `/login/logout`, method: "post"}),
      }),
    }
  )),
  overrideExisting: false
})


export const {
  useGetLoginConfigurationQuery,
  useGetProfileMutation,
  useLoginOAuthMutation,
  useLoginCredentialsMutation,
  useLogoutMutation,
} = extendedApi
