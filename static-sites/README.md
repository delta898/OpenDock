# Static web roots

Each static route serves files from a directory named after its hostname. For
example, `make route add docs.example.net static` creates
`static-sites/docs.example.net/`. Place the HTML, CSS, JavaScript, and assets
there, then run `make launch docs.example.net` to apply Caddy and Cloudflare
routing. OpenDock does not build the site or run a separate web-server process;
Caddy reads the files directly through a read-only mount.
