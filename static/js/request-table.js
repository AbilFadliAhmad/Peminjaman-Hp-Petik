function requestTable() {

    const table = document.getElementById("requestsTable");

    if (!table) return;

    const tbody = table.querySelector("tbody");

    const rows = Array.from(tbody.querySelectorAll("tr"));
    if (rows.length === 0) return;

    let filteredRows = [...rows];

    let currentPage = 1;

    let rowsPerPage = parseInt(document.getElementById("pageLength").value) || 10;

    function renderTable() {

        const start = (currentPage - 1) * rowsPerPage;
        const end = start + rowsPerPage;

        rows.forEach(row => row.style.display = "none");

        filteredRows
            .slice(start, end)
            .forEach(row => {
                row.style.display = "";
            });

        renderPagination();

    }

    function renderPagination() {

        const totalPages = Math.ceil(filteredRows.length / rowsPerPage);
        const container = document.getElementById("paginationButtons");
        const info = document.getElementById("paginationInfo");

        container.innerHTML = "";

        // Previous

        const prev = document.createElement("button");

        prev.textContent = "←";

        prev.className =
            "px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40";

        prev.disabled = currentPage === 1;

        prev.onclick = () => {

            currentPage--;

            renderTable();

        };

        container.appendChild(prev);

        // Number

        for (let i = 1; i <= totalPages; i++) {

            const btn = document.createElement("button");

            btn.textContent = i;

            btn.className =
                i === currentPage
                    ? "px-4 py-2 rounded-lg bg-blue-600 text-white"
                    : "px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-100";

            btn.onclick = () => {

                currentPage = i;

                renderTable();

            };

            container.appendChild(btn);

        }

        // Next

        const next = document.createElement("button");

        next.textContent = "→";

        next.className =
            "px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40";

        next.disabled = currentPage === totalPages;

        next.onclick = () => {

            currentPage++;

            renderTable();

        };

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

    const keyword = document
        .getElementById("searchRequest")
        .value
        .trim()
        .toLowerCase();

    const status = document
        .getElementById("statusFilter")
        .value
        .trim()
        .toUpperCase();

    filteredRows = rows.filter(row => {

        const name = row.children[1].textContent.toLowerCase();

        const reason = row.children[4].textContent.toLowerCase();

        const rowStatus = row.children[5].textContent
            .trim()
            .toUpperCase();

        const matchKeyword =
            keyword === "" ||
            name.includes(keyword) ||
            reason.includes(keyword);

        const matchStatus =
            status === "" ||
            rowStatus.includes(status);

        return matchKeyword && matchStatus;

    });

    currentPage = 1;

    renderTable();

}

    const statusFilter = document.getElementById("statusFilter");

    statusFilter.addEventListener("change", function () {
        const value = this.value.trim().toUpperCase();
        if (value === "") {
            filteredRows = [...rows];
        } else {
            filteredRows = rows.filter(row => {
                const statusCell = row.children[5];
                const status = statusCell.textContent.trim().toUpperCase();
                return status.includes(value);
            });
        }

        currentPage = 1;
        renderTable();
    });

    document
        .getElementById("pageLength")
        .addEventListener("change", function () {

            rowsPerPage = parseInt(this.value);

            currentPage = 1;

            renderTable();

        });
    
    document
        .getElementById("searchRequest")
        .addEventListener("input", applyFilters);

    renderTable();

}

export default requestTable;