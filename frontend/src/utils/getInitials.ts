export const getInitials = (fullName: string | null | undefined): string => {
  if (!fullName) return "";
  const parts = fullName.trim().split(/\s+/);
  if (parts.length > 1) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return fullName.substring(0, 2).toUpperCase();
};
