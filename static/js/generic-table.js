function genericTable(options = {}) {

    const searchColumnIndex = options.searchColumnIndex ?? 1;
    const statusColumnIndex = options.statusColumnIndex ?? null;

    const table = document.getElementById("requestsTable");

    if (!table) return;

    const tbody = table.querySelector("tbody");

    const rows = Array.from(tbody.querySelectorAll("tr"));

    if (rows.length === 0) return;

    let filteredRows = [...rows];

    let currentPage = 1;

    const pageLengthEl = document.getElementById("pageLength");

    let rowsPerPage = parseInt(pageLengthEl?.value) || 10;

    function renderTable() {

        const start = (currentPage - 1) * rowsPerPage;
        const end = start + rowsPerPage;

        rows.forEach(row => row.style.display = "none");

        filteredRows
            .slice(start, end)
            .forEach(row => row.style.display = "");

        renderPagination();

    }

    function renderPagination() {

        const totalPages = Math.ceil(filteredRows.length / rowsPerPage);

        const container = document.getElementById("paginationButtons");
        const info = document.getElementById("paginationInfo");

        if (!container || !info) return;

        container.innerHTML = "";

        const prev = document.createElement("button");
        prev.textContent = "←";
        prev.className = "px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40";
        prev.disabled = currentPage === 1;
        prev.onclick = () => { currentPage--; renderTable(); };
        container.appendChild(prev);

        for (let i = 1; i <= totalPages; i++) {
            const btn = document.createElement("button");
            btn.textContent = i;
            btn.className = i === currentPage
                ? "px-4 py-2 rounded-lg bg-blue-600 text-white"
                : "px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-100";
            btn.onclick = () => { currentPage = i; renderTable(); };
            container.appendChild(btn);
        }

        const next = document.createElement("button");
        next.textContent = "→";
        next.className = "px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40";
        next.disabled = currentPage === totalPages || totalPages === 0;
        next.onclick = () => { currentPage++; renderTable(); };
        container.appendChild(next);

        const start = filteredRows.length === 0 ? 0 : ((currentPage - 1) * rowsPerPage) + 1;
        const end = Math.min(currentPage * rowsPerPage, filteredRows.length);

        info.innerHTML = `
            Menampilkan
            <span class="font-semibold">${start}</span>
            -
            <span class="font-semibold">${end}</span>
            dari
            <span class="font-semibold">${filteredRows.length}</span>
            data
        `;

    }

    function applyFilters() {

        const searchEl = document.getElementById("searchRequest");
        const statusEl = document.getElementById("statusFilter");

        const keyword = searchEl ? searchEl.value.trim().toLowerCase() : "";
        const status = statusEl ? statusEl.value.trim().toUpperCase() : "";

        filteredRows = rows.filter(row => {

            const text = (row.children[searchColumnIndex]?.textContent || "")
                .trim()
                .toLowerCase();

            const matchKeyword = keyword === "" || text.includes(keyword);

            let matchStatus = true;

            if (statusColumnIndex !== null && status !== "") {
                const rowStatus = (row.children[statusColumnIndex]?.textContent || "")
                    .trim()
                    .toUpperCase();
                matchStatus = rowStatus.includes(status);
            }

            return matchKeyword && matchStatus;

        });

        currentPage = 1;

        renderTable();

    }

    document.getElementById("searchRequest")?.addEventListener("input", applyFilters);
    document.getElementById("statusFilter")?.addEventListener("change", applyFilters);

    pageLengthEl?.addEventListener("change", function () {
        rowsPerPage = parseInt(this.value);
        currentPage = 1;
        renderTable();
    });

    renderTable();

}

export default genericTable;
