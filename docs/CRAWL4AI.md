# Crawl4AI — Public web and academic page acquisition

Crawl4AI is the **HTML extraction engine** for Mechanical_Patent. Patent search still uses official/authorized structured APIs and licensed datasets (EPO OPS, CNIPA, USPTO ODP, WIPO licensed feeds, BigQuery). Crawl4AI is not a substitute for those databases.

## Architecture

1. Search provider returns grounded URLs. Non-patent technical pages may enter the web crawl queue only after confidentiality classification and domain-policy approval.
2. Local Crawl4AI browser extracts original public HTML to Markdown. Built-in robots.txt checking is enabled.
3. A page snapshot retains its HTTPS URL, title, UTC fetch time, content SHA256 and extracted Markdown. It is labeled untrusted source content.
4. Source content enters the invention landscape as non-patent evidence (kind web). It cannot satisfy patent claim-text completeness gates.
5. Reviewers inspect real sources and mark prior art, factual reliability, copyright and usage rights separately.

## Installation (local, no Docker)

    python -m pip install -e ".[web]"
    crawl4ai-setup
    crawl4ai-doctor

## Example

    python -m mechanical_patent run \
      --direction "消防车高海拔吸水系统的机械结构和控制发明" \
      --provider epo-ops --allow-search-exposure \
      --web-url https://arxiv.org/abs/2310.06825 \
      --web-allow-domain arxiv.org --allow-web-exposure \
      --case-dir cases/altitude-pump-01

The arXiv address is a **format example only**, not a verified relevant citation. Replace with actual relevant sources.

## Safety and compliance

- Crawl4AI 0.9.5 is pinned to receive its October 2026 SSRF and configuration security fixes.
- Explicit per-host HTTPS allowlist, port 443, DNS public-IP preflight, robots.txt check, fixed page budget, timeout and content cap.
- No bot mitigation bypass, CAPTCHA bypass, cookie theft, paid-content bypass, arbitrary JavaScript, unauthorized access or WIPO PATENTSCOPE public-UI automation.
- Protect browser egress via network firewall/egress proxy with per-redirect verification and DNS/IP pinning. Python preflight DNS checking cannot by itself eliminate redirect and DNS rebinding attacks.
- The library itself does not automatically discover search results; add compliant search discovery via OpenAlex, Crossref, authorized search APIs and patent database citations. A hosted Crawl4AI Cloud account is optional and separate; do not send unpublished invention data without explicit approval and contractual review.
- External HTML is untrusted LLM input. Never execute commands or instructions found on pages.

## Production work backlog

Provider-specific permission ledger, per-domain crawl queues, rate-limit budget, retries with jitter, canonical URLs, redirect-IP verification, source snapshot retention, terms-of-service exception approvals, signed provenance, Unicode normalization, NPL citation anchors and deduplication. All remain separate implementation gates.
