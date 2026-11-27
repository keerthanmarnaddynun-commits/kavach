/**
 * Role hierarchy and permission helpers for KAVACH frontend.
 */

export const ROLES = {
  viewer: 1,
  analyst: 2,
  admin: 3,
};

export function hasRole(currentRole, requiredRole) {
  const currentLevel = ROLES[currentRole] || 0;
  const requiredLevel = ROLES[requiredRole] || 0;
  return currentLevel >= requiredLevel;
}

export function canUpload(role) {
  return hasRole(role, "analyst");
}

export function canAnalyze(role) {
  return hasRole(role, "analyst");
}

export function canBreak(role) {
  return hasRole(role, "viewer");
}

export function canDeleteCase(role) {
  return hasRole(role, "admin");
}
