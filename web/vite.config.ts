import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// BASE_PATH lets the same build run from a sub-path (GitHub Pages) or from "/" (Render, local).
export default defineConfig({ base: process.env.BASE_PATH ?? "/", plugins: [react()], server: { port: 5180, host: true } });
