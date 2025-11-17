function goPage(page) {
    if (page < 1) return;
    document.getElementById("pageInput").value = page;
    document.getElementById("pfForm").submit();
}
