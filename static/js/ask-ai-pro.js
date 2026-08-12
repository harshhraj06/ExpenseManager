(() => {
    "use strict";

    const stream =
        document.getElementById(
            "aiChatStream"
        );

    const input =
        document.getElementById(
            "aiQuestion"
        );

    const form =
        document.getElementById(
            "aiQuestionForm"
        );

    const send =
        document.getElementById(
            "aiSend"
        );


    /* Scroll to latest response */
    if (stream) {
        stream.scrollTop =
            stream.scrollHeight;
    }


    /* Auto-resize textarea */
    function resizeInput() {
        if (!input) return;

        input.style.height =
            "auto";

        input.style.height =
            Math.min(
                input.scrollHeight,
                130
            ) + "px";
    }


    if (input) {

        input.addEventListener(
            "input",
            resizeInput
        );


        /* Enter sends, Shift+Enter new line */
        input.addEventListener(
            "keydown",
            (event) => {

                if (
                    event.key === "Enter"
                    && !event.shiftKey
                ) {

                    event.preventDefault();

                    if (
                        input.value.trim()
                        && form
                    ) {
                        form.requestSubmit();
                    }
                }

            }
        );
    }


    /* Suggested prompts */
    document.querySelectorAll(
        ".ai-prompt"
    ).forEach((button) => {

        button.addEventListener(
            "click",
            () => {

                if (!input) return;

                input.value =
                    button.dataset.question
                    || "";

                resizeInput();

                input.focus();

            }
        );

    });


    /* Loading state */
    if (form) {

        form.addEventListener(
            "submit",
            () => {

                if (send) {
                    send.disabled = true;
                    send.style.opacity = ".55";
                }

            }
        );
    }


    /* ==================================================
       12-MONTH TREND
       ================================================== */

    const trendButton =
        document.getElementById(
            "aiTrendToggle"
        );

    const trendPanel =
        document.getElementById(
            "aiTrendPanel"
        );

    const trendClose =
        document.getElementById(
            "aiTrendClose"
        );

    let trendLoaded = false;


    async function loadTrend() {

        if (
            trendLoaded
            || !window.Chart
        ) {
            return;
        }


        const canvas =
            document.getElementById(
                "aiTrendChart"
            );

        if (!canvas) return;


        try {

            const response =
                await fetch(
                    "/api/monthly_trend",
                    {
                        credentials:
                            "same-origin"
                    }
                );


            if (!response.ok) {
                return;
            }


            const result =
                await response.json();

            const trend =
                result.trend || [];


            new Chart(
                canvas,
                {
                    type: "line",

                    data: {

                        labels:
                            trend.map(
                                row =>
                                    row.label
                            ),

                        datasets: [
                            {
                                label:
                                    "Income",

                                data:
                                    trend.map(
                                        row =>
                                            row.income
                                    ),

                                borderWidth: 2,
                                tension: .32,
                                pointRadius: 2
                            },

                            {
                                label:
                                    "Expenses",

                                data:
                                    trend.map(
                                        row =>
                                            row.expense
                                    ),

                                borderWidth: 2,
                                tension: .32,
                                pointRadius: 2
                            }
                        ]
                    },

                    options: {

                        responsive: true,

                        maintainAspectRatio:
                            false,

                        interaction: {
                            intersect: false,
                            mode: "index"
                        },

                        plugins: {

                            legend: {

                                labels: {
                                    color:
                                        "#8793a0",

                                    usePointStyle:
                                        true,

                                    boxWidth: 10
                                }
                            }
                        },

                        scales: {

                            x: {

                                ticks: {
                                    color:
                                        "#65717d"
                                },

                                grid: {
                                    color:
                                        "rgba(255,255,255,.04)"
                                }
                            },

                            y: {

                                beginAtZero:
                                    true,

                                ticks: {
                                    color:
                                        "#65717d"
                                },

                                grid: {
                                    color:
                                        "rgba(255,255,255,.04)"
                                }
                            }
                        }
                    }
                }
            );


            trendLoaded =
                true;

        } catch (error) {

            console.debug(
                "AI trend unavailable"
            );

        }
    }


    if (
        trendButton
        && trendPanel
    ) {

        trendButton.addEventListener(
            "click",
            async () => {

                trendPanel.hidden =
                    false;

                await loadTrend();

                trendPanel.scrollIntoView(
                    {
                        behavior:
                            "smooth",

                        block:
                            "nearest"
                    }
                );

            }
        );
    }


    if (
        trendClose
        && trendPanel
    ) {

        trendClose.addEventListener(
            "click",
            () => {

                trendPanel.hidden =
                    true;

            }
        );
    }


    /* ==================================================
       NOTIFICATION FUNCTIONALITY
       Full visual redesign comes next.
       ================================================== */

    const notifButton =
        document.getElementById(
            "notifBellBtn"
        );

    const notifDropdown =
        document.getElementById(
            "notifDropdown"
        );


    if (
        notifButton
        && notifDropdown
    ) {

        notifButton.addEventListener(
            "click",
            (event) => {

                event.stopPropagation();

                notifDropdown.classList.toggle(
                    "open"
                );

            }
        );


        document.addEventListener(
            "click",
            (event) => {

                if (
                    !notifDropdown.contains(
                        event.target
                    )
                    &&
                    !notifButton.contains(
                        event.target
                    )
                ) {

                    notifDropdown.classList.remove(
                        "open"
                    );
                }

            }
        );


        notifDropdown
        .querySelectorAll(
            ".notif-item"
        )
        .forEach((item) => {

            item.addEventListener(
                "click",
                async () => {

                    const id =
                        item.dataset.notifId;

                    if (!id) return;


                    const response =
                        await fetch(
                            "/notifications/mark_read/"
                            + id,
                            {
                                method: "POST"
                            }
                        );


                    if (response.ok) {
                        item.classList.remove(
                            "notif-unread"
                        );
                    }

                }
            );

        });


        const markAll =
            document.getElementById(
                "notifMarkAllRead"
            );


        if (markAll) {

            markAll.addEventListener(
                "click",
                async (event) => {

                    event.stopPropagation();


                    const response =
                        await fetch(
                            "/notifications/mark_all_read",
                            {
                                method: "POST"
                            }
                        );


                    if (response.ok) {

                        notifDropdown
                        .querySelectorAll(
                            ".notif-unread"
                        )
                        .forEach((item) => {

                            item.classList.remove(
                                "notif-unread"
                            );

                        });


                        const badge =
                            notifButton.querySelector(
                                ".notif-badge"
                            );

                        if (badge) {
                            badge.remove();
                        }


                        markAll.remove();
                    }

                }
            );
        }
    }

})();
