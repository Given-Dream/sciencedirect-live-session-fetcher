# Troubleshooting

## `no_pdf_metadata`

Common causes:

- the page is still on a bot verification or sign-in screen
- the article page did not fully load
- the session can see the article landing page but not the PDF metadata

What to do:

1. keep the same Chrome or Edge window open
2. manually open the target article in that window
3. click `View PDF`
4. rerun only the failed rows

## `viewer_extract_failed`

Common causes:

- the in-browser PDF viewer did not finish loading
- the tab opened a non-PDF error page
- the session expired between the article page and the PDF viewer page

What to do:

- increase `PageWaitSeconds`
- keep `InterItemSleepSeconds` at `5+`
- manually test one failed DOI in the same session

## The browser keeps showing bot verification pages

Likely causes:

- the session is not fully authorized yet
- the current network path is triggering a bot verification page
- the browser profile is too clean and needs a complete sign-in flow

What to do:

- finish the bot verification in the same Chrome or Edge window
- open a real article and its PDF manually first
- avoid opening too many articles quickly

## The fetcher cannot attach to the session

Check:

- Chrome or Edge was launched with `--remote-debugging-port`
- the port matches your command, for example `9222`
- the Chrome or Edge window is still open

If needed, start a fresh Chrome session on macOS with:

```bash
bash ./scripts/launch_chrome_clone_remote_debug_macos.sh \
  --direct-connection \
  --disable-extensions \
  --one-shot-profile
```

## Existing main Chrome or Edge windows interfere

If you reuse a live profile, close all browser windows first. The recommended path is to use the dedicated launcher and isolated user-data directory instead.

## Article rows with only DOI and no candidate URLs

This is supported. The fetcher will open `https://doi.org/<doi>` first.

## Network-specific access problems

This workflow does not solve access or routing problems by itself. If your institution requires a specific network path, VPN split tunneling, or campus egress route, fix that first and then rerun the workflow.
