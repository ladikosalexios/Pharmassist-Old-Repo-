import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./lib/auth";
import { AdminAuthProvider } from "./lib/adminAuth";
import { ToastProvider } from "./components/Toast";
import { ModalRegistryProvider } from "./lib/keyboard";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <AdminAuthProvider>
          <ToastProvider>
            <ModalRegistryProvider>
              <App />
            </ModalRegistryProvider>
          </ToastProvider>
        </AdminAuthProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
