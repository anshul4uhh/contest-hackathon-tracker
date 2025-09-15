async function fetchContests(type = "", status = "", search = "") {
  let url = "http://127.0.0.1:8000/api/all";
  const params = [];
  if (type) params.push(`type=${type}`);
  if (status) params.push(`status=${status}`);
  if (params.length) url += `?${params.join("&")}`;

  const res = await fetch(url);
  const data = await res.json();

  // Apply search filter on frontend
  const filtered = data.filter(item =>
    item.title.toLowerCase().includes(search.toLowerCase()) ||
    item.platform.toLowerCase().includes(search.toLowerCase())
  );

  displayCards(filtered);
}

function displayCards(data) {
  const container = document.getElementById("cards");
  container.innerHTML = "";

  if (!data.length) {
    container.innerHTML = "<p style='text-align:center;'>No results found.</p>";
    return;
  }

  data.forEach(item => {
    const card = document.createElement("div");
    card.className = "card";

    card.innerHTML = `
      <h3>${item.title}</h3>
      <p><strong>Platform:</strong> ${item.platform}</p>
      <p><strong>Start:</strong> ${item.start_date || "N/A"}</p>
      <p><strong>End:</strong> ${item.end_date || "N/A"}</p>
      <p><strong>Status:</strong> ${item.status || item.phase || "N/A"}</p>
      <a href="${item.apply_link}" target="_blank">Apply / Open</a>
    `;

    container.appendChild(card);
  });
}

// Apply filters button
document.getElementById("applyFilters").addEventListener("click", () => {
  const type = document.getElementById("type").value;
  const status = document.getElementById("status").value;
  const search = document.getElementById("search").value;
  fetchContests(type, status, search);
});

// Load on page start
fetchContests();
