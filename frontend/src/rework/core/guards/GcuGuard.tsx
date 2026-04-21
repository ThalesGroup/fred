import { PropsWithChildren } from "react";
import GcuPage from "@components/pages/GcuPage/GcuPage.tsx";
import { controlPlaneApi } from "../../../slices/controlPlane/controlPlaneApi.ts";
import { useDispatch } from "react-redux";
import { UserDetails } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useFrontendProperties } from "src/hooks/useFrontendProperties.ts";

export default function GcuGuard({ children }: PropsWithChildren) {
  const { gcuVersion } = useFrontendProperties();
  const dispatch = useDispatch();
  const result = controlPlaneApi.endpoints["getUserDetailsControlPlaneV1UserGet"].useQuery(undefined);

  if (result.isLoading || result.isUninitialized) {
    const fetchUserDetailsAction = controlPlaneApi.endpoints["getUserDetailsControlPlaneV1UserGet"].initiate(undefined);
    throw dispatch(fetchUserDetailsAction as any);
  }
  const userDetails: UserDetails = result.data;

  if (!gcuVersion || userDetails && userDetails.cguValidated.toString() == gcuVersion) {
    return <>{children}</>;
  }

  return <GcuPage />;
}
