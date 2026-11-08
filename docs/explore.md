# Explore any repo

Pick a Xania repository and branch, and optionally a second one to compare it with. The explorer downloads
the area files and the C++ tables it reads straight from GitHub, then runs the same analysis as this site
**in your browser**. You get the dashboard, every system page, the bugs and, for two sides, the comparison.

<div id="xe-app" class="xe-app"></div>

<noscript>The explorer needs JavaScript. The prebuilt versions in the navigation work without it.</noscript>

??? info "How it works, and its limits"

    - **Public repositories only.** Requests go to GitHub anonymously, which allows 60 API calls an hour from
      one network. A run takes about 3 per side; downloads come from `raw.githubusercontent.com` and don't count.
    - **The first visit** downloads the Python runtime (Pyodide, about 5 MB compressed); the browser caches it.
      A run takes around 10–30 seconds per side depending on the device. Files and results are cached per
      commit, so repeating a run is instant until the branch moves.
    - **Not a Xania repo?** The explorer checks the file list for `area/area.lst` before downloading anything.
      A Xania-like repo that lacks some of the C++ files gets those systems marked unavailable, and the rest
      still runs.
    - **Nothing leaves your browser.** There's no server: the analysis runs locally and nothing is stored
      anywhere but this browser's cache.
    - **Shareable.** The address bar holds the comparison (`?base=owner/repo@branch&head=…`), so you can
      bookmark it or send it to someone.
    - **Too slow, or failing on this device?** A maintainer can build the same pages on GitHub instead. The
      explorer shows the exact command when a run fails or takes long, and finished builds are listed under
      [Builds on GitHub](builds.md).
