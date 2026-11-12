import type { store } from "../../../../common/store";
import { pptBuilderCapabilityApi, type PlatformTemplateResponse } from "./api/pptBuilderCapabilityOpenApi";

export function updatePlatformCache(dispatch: typeof store.dispatch, next: PlatformTemplateResponse) {
  const running = dispatch(pptBuilderCapabilityApi.util.getRunningQueryThunk("getPptBuilderPlatform", undefined));
  // An older poll must not overwrite the mutation response when it completes.
  running?.abort();
  void dispatch(pptBuilderCapabilityApi.util.upsertQueryData("getPptBuilderPlatform", undefined, next));
}
