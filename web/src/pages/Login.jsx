import React, { useState, useEffect } from "react";
import { setToken, getToken, request } from "../api/client.js";

export function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorText, setErrorText] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (token) {
      request("/auth/me")
        .then(() => onLoginSuccess())
        .catch(() => {});
    }
  }, [onLoginSuccess]);

  async function handleLogin(e) {
    if (e) e.preventDefault();
    if (!username || !password) return;

    setErrorText("");
    setLoading(true);

    try {
      const res = await request("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (res && res.access_token) {
        setToken(res.access_token);
        onLoginSuccess();
      }
    } catch (err) {
      setErrorText(err.message || "Login failed");
    } finally {
      setLoading(false);
      // Clear password from form state immediately after attempt
      setPassword("");
    }
  }

  return (
    <div style={{ maxWidth: "320px", margin: "60px auto" }}>
      <h2 style={{ marginBottom: "16px", fontSize: "16px", fontWeight: "600" }}>Login to KAVACH</h2>
      {errorText && (
        <div className="error-text" style={{ marginBottom: "12px" }}>
          {errorText}
        </div>
      )}
      <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <div>
          <label style={{ display: "block", marginBottom: "4px", color: "var(--muted)" }}>
            User Name
          </label>
          <input
            type="text"
            style={{ width: "100%" }}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
            required
            autoFocus
          />
        </div>
        <div>
          <label style={{ display: "block", marginBottom: "4px", color: "var(--muted)" }}>
            Password
          </label>
          <input
            type="password"
            style={{ width: "100%" }}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            required
          />
        </div>
        <button
          type="submit"
          className="primary"
          style={{ marginTop: "8px" }}
          disabled={loading}
        >
          {loading ? "Authenticating..." : "Login"}
        </button>
      </form>
    </div>
  );
}

export default Login;
