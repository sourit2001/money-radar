const state = { opportunities: [], meta: { total: 0, channels: [], subreddits: [] } };
const els = {
  opportunities: document.querySelector("#opportunities"),
  summary: document.querySelector("#summary"),
  refresh: document.querySelector("#refresh"),
  channel: document.querySelector("#channel"),
  subreddit: document.querySelector("#subreddit"),
  minScore: document.querySelector("#min-score"),
  scoreLabel: document.querySelector("#score-label"),
  search: document.querySelector("#search"),
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[char]);
}

function fillSelect(select, values, firstLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${firstLabel}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = values.includes(current) ? current : "";
}

function queryString() {
  const params = new URLSearchParams();
  if (els.channel.value) params.set("channel", els.channel.value);
  if (els.subreddit.value) params.set("subreddit", els.subreddit.value);
  if (els.search.value.trim()) params.set("search", els.search.value.trim());
  params.set("min_score", els.minScore.value);
  return params.toString();
}

async function loadOpportunities() {
  els.summary.textContent = "Loading market opportunities...";
  const response = await fetch(`/api/opportunities?${queryString()}`);
  if (!response.ok) {
    els.summary.textContent = "Could not load opportunities from the local API.";
    return;
  }
  const payload = await response.json();
  state.opportunities = payload.opportunities;
  state.meta = payload.meta;
  fillSelect(els.channel, state.meta.channels, "All channels");
  fillSelect(els.subreddit, state.meta.subreddits, "All subreddits");
  render();
}

function render() {
  els.scoreLabel.textContent = `${els.minScore.value}+`;
  els.summary.textContent = `${state.opportunities.length} market themes from ${state.meta.total} saved posts`;
  if (!state.opportunities.length) {
    els.opportunities.innerHTML = `<div class="empty">No grouped opportunities yet. Run a fetch or lower the evidence filter.</div>`;
    return;
  }
  els.opportunities.innerHTML = state.opportunities.map((item) => `
    <article class="opportunity">
      <div class="opportunity-header">
        <div>
          <div class="eyebrow">${escapeHtml(item.evidence_level)} evidence · ${escapeHtml(item.post_count)} source posts</div>
          <h2>${escapeHtml(item.title)}</h2>
        </div>
        <div class="market-score">${escapeHtml(item.market_score)}/10</div>
      </div>
      <p class="why-now">${escapeHtml(item.why_now)}</p>
      <div class="evidence-grid">
        <div><span>Communities</span><strong>${escapeHtml(item.subreddits.join(", "))}</strong></div>
        <div><span>Paid signals</span><strong>${escapeHtml(item.paid_signal_count)}</strong></div>
        <div><span>Failed/workaround signals</span><strong>${escapeHtml(item.failed_solution_count)}</strong></div>
        <div><span>Pain signals</span><strong>${escapeHtml(item.pain_signal_count)}</strong></div>
      </div>
      <div class="gap"><strong>Current gap:</strong> ${escapeHtml(item.current_workaround)}</div>
      <div class="next-action"><strong>Next action:</strong> ${escapeHtml(item.next_action)}</div>
      <details>
        <summary>View representative Reddit posts</summary>
        <div class="source-posts">${item.posts.map((post) => `
          <a class="source-post" href="${escapeHtml(post.permalink)}" target="_blank" rel="noreferrer">
            <strong>${escapeHtml(post.title)}</strong>
            <span>r/${escapeHtml(post.subreddit)} · ${escapeHtml(post.num_comments)} comments</span>
          </a>
        `).join("")}</div>
      </details>
    </article>
  `).join("");
}

["change", "input"].forEach((eventName) => {
  els.channel.addEventListener(eventName, loadOpportunities);
  els.subreddit.addEventListener(eventName, loadOpportunities);
  els.minScore.addEventListener(eventName, loadOpportunities);
  els.search.addEventListener(eventName, () => {
    window.clearTimeout(els.search._timer);
    els.search._timer = window.setTimeout(loadOpportunities, 180);
  });
});
els.refresh.addEventListener("click", loadOpportunities);
loadOpportunities();
