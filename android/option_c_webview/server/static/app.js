// PS4Cheater WebView app — JS minimal

const API = (path, opts = {}) => fetch(path, {
  headers: {"Content-Type": "application/json"},
  ...opts,
}).then(r => r.json());

// ---------------------------------------------------------------------------
// Estado UI
// ---------------------------------------------------------------------------

function setStatus(connected, ip = "", port = 0, pid = 0, procName = "") {
  const badge = document.getElementById("status-badge");
  const line = document.getElementById("status-line");
  if (connected) {
    badge.className = "badge badge-on";
    line.textContent = `Conectado a ${ip}:${port}` + (pid ? ` | PID ${pid} (${procName})` : "");
    document.querySelectorAll('.tab-btn').forEach(b => b.disabled = false);
  } else {
    badge.className = "badge badge-off";
    line.textContent = "Desconectado";
    document.querySelectorAll('.tab-btn').forEach(b => {
      if (b.dataset.tab !== "connect") b.disabled = true;
    });
  }
}

function refreshStatus() {
  API("/api/status").then(s => {
    setStatus(s.connected, s.ip, s.port, s.pid, s.proc_name);
  });
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById("tab-" + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === "procs") refreshProcs();
    if (btn.dataset.tab === "cheats") refreshCheats();
  });
});

// ---------------------------------------------------------------------------
// Conexión
// ---------------------------------------------------------------------------

document.getElementById("btn-connect").addEventListener('click', async () => {
  const ip = document.getElementById("conn-ip").value.trim();
  const port = parseInt(document.getElementById("conn-port").value) || 744;
  if (!ip) { showMsg("conn-msg", "IP requerida", "err"); return; }
  showMsg("conn-msg", "Conectando…");
  const r = await API("/api/connect", {
    method: "POST",
    body: JSON.stringify({ip, port}),
  });
  if (r.ok) {
    showMsg("conn-msg", `Conectado. Versión: ${r.version}`, "ok");
    refreshStatus();
    document.getElementById("btn-connect").disabled = true;
    document.getElementById("btn-disconnect").disabled = false;
  } else {
    showMsg("conn-msg", `Error: ${r.error}`, "err");
  }
});

document.getElementById("btn-disconnect").addEventListener('click', async () => {
  await API("/api/disconnect", {method: "POST"});
  showMsg("conn-msg", "Desconectado", "ok");
  refreshStatus();
  document.getElementById("btn-connect").disabled = false;
  document.getElementById("btn-disconnect").disabled = true;
});

// ---------------------------------------------------------------------------
// Procesos
// ---------------------------------------------------------------------------

async function refreshProcs() {
  const r = await API("/api/procs");
  if (!r.ok) { return; }
  const tbody = document.querySelector("#procs-table tbody");
  tbody.innerHTML = "";
  for (const p of r.procs) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${p.pid}</td><td>${p.name}</td>
      <td><button onclick="attachProc(${p.pid})">Attach</button></td>`;
    tbody.appendChild(tr);
  }
}

document.getElementById("btn-refresh-procs").addEventListener('click', refreshProcs);

window.attachProc = async function(pid) {
  const r = await API("/api/attach", {
    method: "POST",
    body: JSON.stringify({pid}),
  });
  if (r.ok) {
    showMsg("conn-msg", `Attacheado a ${r.name} (${r.section_count} secciones)`, "ok");
    refreshStatus();
  } else {
    showMsg("conn-msg", `Error: ${r.error}`, "err");
  }
};

// ---------------------------------------------------------------------------
// Scan
// ---------------------------------------------------------------------------

document.getElementById("btn-scan-new").addEventListener('click', async () => {
  const value_type = document.getElementById("scan-type").value;
  const compare_type = document.getElementById("scan-cmp").value;
  const value1 = document.getElementById("scan-v1").value;
  const value2 = document.getElementById("scan-v2").value;
  showMsg("scan-msg", "Escaneando…");
  const r = await API("/api/scan/new", {
    method: "POST",
    body: JSON.stringify({value_type, compare_type, value1, value2}),
  });
  if (r.ok) {
    showMsg("scan-msg", `Scan completado: ${r.count} resultado(s)`, "ok");
    refreshResults();
  } else {
    showMsg("scan-msg", `Error: ${r.error}`, "err");
  }
});

document.getElementById("btn-scan-next").addEventListener('click', async () => {
  const compare_type = document.getElementById("scan-cmp").value;
  const value1 = document.getElementById("scan-v1").value;
  const value2 = document.getElementById("scan-v2").value;
  const r = await API("/api/scan/next", {
    method: "POST",
    body: JSON.stringify({compare_type, value1, value2}),
  });
  if (r.ok) {
    showMsg("scan-msg", `Next-scan: ${r.count} resultado(s)`, "ok");
    refreshResults();
  } else {
    showMsg("scan-msg", `Error: ${r.error}`, "err");
  }
});

document.getElementById("btn-scan-results").addEventListener('click', refreshResults);

async function refreshResults() {
  const r = await API("/api/scan/results?limit=50");
  if (!r.ok) { return; }
  const tbody = document.querySelector("#results-table tbody");
  tbody.innerHTML = "";
  r.results.forEach((res, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${i+1}</td>
      <td><code>0x${res.address.toString(16).toUpperCase().padStart(16, "0")}</code></td>
      <td>${res.value} <span class="dim">(${res.value_hex})</span></td>`;
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------------------
// Memoria
// ---------------------------------------------------------------------------

document.getElementById("btn-read").addEventListener('click', async () => {
  const address = document.getElementById("mem-addr").value;
  const length = parseInt(document.getElementById("mem-len").value) || 16;
  const r = await API("/api/read", {
    method: "POST",
    body: JSON.stringify({address, length}),
  });
  if (r.ok) {
    const hex = r.hex;
    let dump = "";
    for (let i = 0; i < hex.length; i += 32) {
      const chunk = hex.substring(i, i+32);
      const addr = parseInt(address, 16) + i/2;
      let hexStr = "";
      for (let j = 0; j < chunk.length; j += 2) {
        hexStr += chunk.substring(j, j+2) + " ";
      }
      dump += `0x${addr.toString(16).toUpperCase().padStart(16, "0")}  ${hexStr.padEnd(48)}  |${r.ascii.substring(i/2, i/2+16)}|\n`;
    }
    document.getElementById("mem-dump").textContent = dump;
  } else {
    showMsg("mem-msg", `Error: ${r.error}`, "err");
  }
});

document.getElementById("btn-write").addEventListener('click', async () => {
  const address = document.getElementById("mem-addr").value;
  const hex_bytes = document.getElementById("mem-write").value;
  const r = await API("/api/write", {
    method: "POST",
    body: JSON.stringify({address, hex_bytes}),
  });
  if (r.ok) {
    showMsg("mem-msg", `Escritos ${r.written} bytes`, "ok");
  } else {
    showMsg("mem-msg", `Error: ${r.error}`, "err");
  }
});

// ---------------------------------------------------------------------------
// Cheats
// ---------------------------------------------------------------------------

document.getElementById("btn-cheat-add").addEventListener('click', async () => {
  const address = document.getElementById("cheat-addr").value;
  const value_type = document.getElementById("cheat-type").value;
  const value = document.getElementById("cheat-val").value;
  const description = document.getElementById("cheat-desc").value;
  const r = await API("/api/cheats/add", {
    method: "POST",
    body: JSON.stringify({address, value_type, value, description}),
  });
  if (r.ok) {
    refreshCheats();
    document.getElementById("cheat-addr").value = "";
    document.getElementById("cheat-val").value = "";
    document.getElementById("cheat-desc").value = "";
  }
});

async function refreshCheats() {
  const r = await API("/api/cheats");
  if (!r.ok) return;
  const tbody = document.querySelector("#cheats-table tbody");
  tbody.innerHTML = "";
  r.cheats.forEach(c => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${c.id}</td>
      <td><code>0x${c.address.toString(16).toUpperCase().padStart(16, "0")}</code></td>
      <td>${c.value_type}</td>
      <td>${c.value}</td>
      <td><input type="checkbox" ${c.frozen ? "checked" : ""} onchange="toggleFreeze(${c.id}, this.checked)"></td>
      <td>${c.description || ""}</td>
      <td><button class="danger" onclick="deleteCheat(${c.id})">X</button></td>`;
    tbody.appendChild(tr);
  });
}

window.toggleFreeze = async function(id, frozen) {
  await API("/api/cheats/freeze", {
    method: "POST",
    body: JSON.stringify({id, frozen}),
  });
};

window.deleteCheat = async function(id) {
  await API(`/api/cheats/${id}`, {method: "DELETE"});
  refreshCheats();
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function showMsg(id, text, kind = "") {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = "msg " + kind;
}

// Init
refreshStatus();
setInterval(refreshStatus, 5000);
