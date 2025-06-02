// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { apiSlice } from "../frugalit/slices/api";

export interface LoginConfiguration {
  openId: string;
}

export interface UserProfile {
  name: string;
  permissions: string[];
  username: string;
  email: string;
}

export interface Credentials {
  username: string;
  password: string;
}

const extendedApi = apiSlice.injectEndpoints({
  endpoints: (build) => ({
    getLoginConfiguration: build.query<LoginConfiguration, { redirectUrl: string }>({
      query: (arg) =>
        `/login/configuration${arg.redirectUrl ? `?redirectUrl=${encodeURIComponent(arg.redirectUrl)}` : ""}`,
    }),
    getProfile: build.mutation<UserProfile, void>({
      query: (_) => `/login/profile`,
    }),
    loginOAuth: build.mutation<void, { code: string; redirectUrl: string }>({
      query: (arg) => ({ url: `/login/oauth`, method: "post", body: arg }),
    }),
    loginCredentials: build.mutation<void, Credentials>({
      query: (arg) => ({
        url: `/login/credentials`,
        method: "post",
        body: arg,
      }),
    }),
    logout: build.mutation<void, void>({
      query: (_) => ({ url: `/login/logout`, method: "post" }),
    }),
  }),
  overrideExisting: false,
});

export const {
  useGetLoginConfigurationQuery,
  useGetProfileMutation,
  useLoginOAuthMutation,
  useLoginCredentialsMutation,
  useLogoutMutation,
} = extendedApi;
