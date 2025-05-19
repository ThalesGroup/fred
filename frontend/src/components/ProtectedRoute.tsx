import { Outlet } from "react-router-dom";

type ProtectedRouteProps = {
  permission: string;
  children?: React.ReactNode;
};

export const ProtectedRoute = ({ permission, children }: ProtectedRouteProps) => {
  console.debug(`⚠️ ProtectedRoute check skipped. Allowed all access for now. (Requested: ${permission})`);
  return <>{children ?? <Outlet />}</>;
};
