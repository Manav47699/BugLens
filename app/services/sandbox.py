"""
L3 Sandbox Service
------------------
Responsibilities:
  1. Unzip the uploaded project into an isolated workspace directory.
  2. Detect the frontend framework (Next.js / Vite / CRA / unknown).
  3. Install npm dependencies.
  4. Spawn the dev server and wait until it's accepting connections.
  5. Return the local URL for the Playwright agent.
"""

import asyncio
import shutil
import zipfile
from pathlib import Path
from typing import Optional

import aiofiles

from app.core.config import settings
from app.core.logging import get_logger
from app.models.session import Session

log = get_logger(__name__)

# Framework detection heuristics
_FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "nextjs": ["next.config.js", "next.config.mjs", "next.config.ts"],
    "vite": ["vite.config.js", "vite.config.ts", "vite.config.mjs"],
    "react": ["src/App.jsx", "src/App.tsx", "src/main.jsx", "src/main.tsx"],
}

# Dev server launch commands per framework
_DEV_COMMANDS: dict[str, list[str]] = {
    "nextjs": ["npm", "run", "dev"],
    "vite": ["npm", "run", "dev"],
    "react": ["npm", "start"],
    "unknown": ["npm", "run", "dev"],  # try the most common one
}

# Default dev server ports (we'll scan for the actual bound port)
_DEFAULT_PORTS: dict[str, int] = {
    "nextjs": 3000,
    "vite": 5173,
    "react": 3000,
    "unknown": 3000,
}


class SandboxError(Exception):
    pass


class Sandbox:
    def __init__(self, session: Session):
        self.session = session
        self.workspace: Path = settings.workspace_dir / session.id
        self.process: Optional[asyncio.subprocess.Process] = None
        self.url: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def setup(self, zip_path: Path) -> str:
        """Unzip, detect, install, boot. Returns the dev server URL."""
        self._unzip(zip_path)
        framework = self._detect_framework()
        self.session.framework = framework
        self.session.log(f"Detected framework: {framework}")

        await self._npm_install()
        url = await self._start_dev_server(framework)
        self.url = url
        return url

    async def teardown(self) -> None:
        """Kill the dev server and remove the workspace."""
        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except Exception:
                self.process.kill()
            log.info(f"[{self.session.id}] Dev server stopped.")

        if self.workspace.exists():
            shutil.rmtree(self.workspace, ignore_errors=True)
            log.info(f"[{self.session.id}] Workspace removed.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _unzip(self, zip_path: Path) -> None:
        self.session.log("Extracting project archive…")
        self.workspace.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self.workspace)
        except zipfile.BadZipFile as exc:
            raise SandboxError(f"Invalid ZIP file: {exc}") from exc

        # If the ZIP contained a single top-level directory, descend into it
        # so self.workspace always points at the project root (has package.json).
        children = list(self.workspace.iterdir())
        if len(children) == 1 and children[0].is_dir():
            # Move contents up one level
            inner = children[0]
            for item in inner.iterdir():
                shutil.move(str(item), str(self.workspace))
            inner.rmdir()

        if not (self.workspace / "package.json").exists():
            raise SandboxError("No package.json found — is this a Node.js frontend project?")

        self.session.log("Extraction complete.")

    def _detect_framework(self) -> str:
        for framework, signals in _FRAMEWORK_SIGNALS.items():
            for signal in signals:
                if (self.workspace / signal).exists():
                    return framework
        return "unknown"

    async def _npm_install(self) -> None:
        # Remove any bundled node_modules from the zip — always install fresh
        nm = self.workspace / "node_modules"
        if nm.exists():
            import shutil
            shutil.rmtree(nm)
            self.session.log("Removed bundled node_modules — installing fresh.")
        self.session.log("Installing npm dependencies (this may take a moment)…")

        proc = await asyncio.create_subprocess_exec(
            "npm", "install", "--no-prefer-offline",
            cwd=self.workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise SandboxError(f"npm install failed:\n{stderr.decode()[:500]}")

        self.session.log("npm install complete.")

    async def _start_dev_server(self, framework: str) -> str:
        cmd = _DEV_COMMANDS.get(framework, _DEV_COMMANDS["unknown"])
        port = _DEFAULT_PORTS.get(framework, 3000)
        url = f"http://localhost:{port}"

        self.session.log(f"Starting dev server: {' '.join(cmd)}")

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**__import__("os").environ, "PORT": str(port), "BROWSER": "none"},
        )

        # Wait for server to be reachable
        await self._wait_for_server(url)
        self.session.log(f"Dev server ready at {url}")
        return url

    async def _wait_for_server(self, url: str) -> None:
        """Poll until the server responds or we hit the timeout.
        Uses only stdlib — no aiohttp needed.
        Also drains stdout so Vite/CRA do not stall on a full pipe buffer.
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 80

        deadline = asyncio.get_event_loop().time() + settings.dev_server_timeout
        attempt = 0

        async def _drain():
            if self.process and self.process.stdout:
                try:
                    while True:
                        line = await asyncio.wait_for(
                            self.process.stdout.readline(), timeout=1
                        )
                        if not line:
                            break
                        decoded = line.decode(errors="ignore").strip()
                        if decoded:
                            self.session.log(f"[server] {decoded}")
                except Exception:
                    pass

        while asyncio.get_event_loop().time() < deadline:
            attempt += 1
            await _drain()
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=3,
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                return
            except Exception:
                if attempt % 5 == 0:
                    elapsed = int(
                        asyncio.get_event_loop().time()
                        - (deadline - settings.dev_server_timeout)
                    )
                    self.session.log(f"Waiting for dev server... ({elapsed}s elapsed)")
                await asyncio.sleep(3)

        raise SandboxError(
            f"Dev server did not start within {settings.dev_server_timeout}s at {url}. "
            "Check that 'npm run dev' works in your project manually."
        )