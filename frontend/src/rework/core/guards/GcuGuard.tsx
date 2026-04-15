import { PropsWithChildren } from "react";
import GcuPage from "@components/pages/GcuPage/GcuPage.tsx";
import { controlPlaneApi } from "../../../slices/controlPlane/controlPlaneApi.ts";
import { useDispatch } from "react-redux";
import { UserDetails } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";

export default function GcuGuard({ children }: PropsWithChildren) {
  const dispatch = useDispatch();
  const result = controlPlaneApi.endpoints["getUserDetailsControlPlaneV1UserGet"].useQuery(undefined);

  if (result.isLoading || result.isUninitialized) {
    const fetchUserDetailsAction = controlPlaneApi.endpoints["getUserDetailsControlPlaneV1UserGet"].initiate(undefined);
    throw dispatch(fetchUserDetailsAction as any);
  }
  const userDetails: UserDetails = result.data;

  if (userDetails.cguValidated) {
    return <>{children}</>;
  }

  return <GcuPage />;
}
