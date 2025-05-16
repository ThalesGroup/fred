import { Outlet } from "react-router-dom";

export const ProtectedRoute = ({ permission }: { permission: string }) => {
  console.debug(`⚠️ ProtectedRoute check skipped. Allowed all access for now. (Requested: ${permission})`);
  return <Outlet />; // Allows access to all routes for now
};
