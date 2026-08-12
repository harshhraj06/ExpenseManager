(() => {
    "use strict";

    const PIE_COLORS = [
        "#7896C4",
        "#C47E68",
        "#7FA487",
        "#9A7BA8",
        "#B99A5E",
        "#6E98A8",
        "#B56F7D",
        "#75848C"
    ];


    function money(value) {
        return (
            "₹" +
            Number(value || 0).toLocaleString(
                "en-IN",
                {
                    maximumFractionDigits: 2
                }
            )
        );
    }


    function getChart(id) {
        if (
            !window.Chart ||
            typeof Chart.getChart !== "function"
        ) {
            return null;
        }

        return Chart.getChart(id);
    }


    /*
     * IMPORTANT:
     * chart.options is Chart.js's resolved/proxied option object.
     * Do not replace objects on that proxy.
     *
     * chart.config.options is the normal configuration object
     * and is safe for our styling changes.
     */
    function getConfigOptions(chart) {
        if (!chart.config.options) {
            chart.config.options = {};
        }

        return chart.config.options;
    }


    function safeUpdate(chart) {
        try {
            chart.update("none");
        } catch (error) {
            console.warn(
                "Chart style update skipped:",
                error
            );
        }
    }


    /* =====================================================
       EXPENSE PIE CHART
       ===================================================== */

    function stylePie() {
        const chart =
            getChart("expenseChart");

        if (!chart) {
            return false;
        }

        const dataset =
            chart.data?.datasets?.[0];

        if (!dataset) {
            return false;
        }


        dataset.backgroundColor =
            (chart.data.labels || []).map(
                (_, index) =>
                    PIE_COLORS[
                        index %
                        PIE_COLORS.length
                    ]
            );

        dataset.borderColor =
            "#11161c";

        dataset.borderWidth =
            3;

        dataset.hoverBorderColor =
            "#1c232b";

        dataset.hoverBorderWidth =
            3;

        dataset.hoverOffset =
            7;


        const options =
            getConfigOptions(chart);


        options.layout =
            options.layout || {};

        options.layout.padding =
            8;


        options.plugins =
            options.plugins || {};


        options.plugins.legend = {
            position: "right",

            labels: {
                color: "#98a3ae",
                usePointStyle: true,
                pointStyle: "circle",
                boxWidth: 8,
                boxHeight: 8,
                padding: 14,

                font: {
                    size: 11,
                    weight: "500"
                }
            }
        };


        options.plugins.tooltip = {
            backgroundColor: "#171d24",
            titleColor: "#eef1f4",
            bodyColor: "#aeb8c2",

            borderColor:
                "rgba(255,255,255,.10)",

            borderWidth: 1,
            padding: 11,
            displayColors: true,
            boxWidth: 8,
            boxHeight: 8,
            cornerRadius: 9,

            callbacks: {
                label(context) {
                    const value =
                        Number(
                            context.raw || 0
                        );

                    const values =
                        context.dataset.data || [];

                    const total =
                        values.reduce(
                            (sum, item) =>
                                sum +
                                Number(
                                    item || 0
                                ),
                            0
                        );

                    const percent =
                        total
                            ? (
                                value /
                                total *
                                100
                            ).toFixed(1)
                            : "0.0";

                    return (
                        " " +
                        context.label +
                        ": " +
                        money(value) +
                        "  ·  " +
                        percent +
                        "%"
                    );
                }
            }
        };


        safeUpdate(chart);

        return true;
    }


    /* =====================================================
       TREND CHART
       ===================================================== */

    function styleTrendById(id) {
        const chart =
            getChart(id);

        if (!chart) {
            return false;
        }


        const colors = [
            "#79A889",
            "#B96F73"
        ];


        (chart.data?.datasets || [])
        .forEach(
            (dataset, index) => {
                const color =
                    colors[
                        index %
                        colors.length
                    ];

                dataset.borderColor =
                    color;

                dataset.backgroundColor =
                    "transparent";

                dataset.borderWidth =
                    2.4;

                dataset.pointBackgroundColor =
                    color;

                dataset.pointBorderColor =
                    "#10151b";

                dataset.pointBorderWidth =
                    2;

                dataset.pointRadius =
                    3;

                dataset.pointHoverRadius =
                    5;

                dataset.tension =
                    0.35;

                dataset.fill =
                    false;
            }
        );


        const options =
            getConfigOptions(chart);


        options.interaction = {
            intersect: false,
            mode: "index"
        };


        options.plugins =
            options.plugins || {};


        options.plugins.legend = {
            position: "top",
            align: "end",

            labels: {
                color: "#8995a0",
                usePointStyle: true,
                pointStyle: "circle",
                boxWidth: 8,
                boxHeight: 8,
                padding: 14,

                font: {
                    size: 11
                }
            }
        };


        options.plugins.tooltip = {
            backgroundColor: "#171d24",
            titleColor: "#eef1f4",
            bodyColor: "#abb5bf",

            borderColor:
                "rgba(255,255,255,.10)",

            borderWidth: 1,
            padding: 11,
            cornerRadius: 9,

            callbacks: {
                label(context) {
                    return (
                        " " +
                        context.dataset.label +
                        ": " +
                        money(context.raw)
                    );
                }
            }
        };


        options.scales =
            options.scales || {};


        ["x", "y"].forEach(
            (axis) => {
                const scale =
                    options.scales[axis];

                if (!scale) {
                    return;
                }


                scale.border =
                    scale.border || {};

                scale.border.display =
                    false;


                scale.grid =
                    scale.grid || {};

                scale.grid.color =
                    axis === "y"
                        ? "rgba(255,255,255,.055)"
                        : "rgba(255,255,255,.025)";

                scale.grid.drawTicks =
                    false;


                scale.ticks =
                    scale.ticks || {};

                scale.ticks.color =
                    "#687480";

                scale.ticks.padding =
                    9;

                scale.ticks.font = {
                    size: 10
                };


                if (axis === "y") {
                    scale.ticks.callback =
                        function (value) {
                            const number =
                                Number(value);

                            if (
                                Math.abs(number)
                                >= 100000
                            ) {
                                return (
                                    "₹" +
                                    (
                                        number /
                                        100000
                                    ).toFixed(1) +
                                    "L"
                                );
                            }

                            if (
                                Math.abs(number)
                                >= 1000
                            ) {
                                return (
                                    "₹" +
                                    (
                                        number /
                                        1000
                                    ).toFixed(0) +
                                    "k"
                                );
                            }

                            return (
                                "₹" +
                                number
                            );
                        };
                }
            }
        );


        safeUpdate(chart);

        return true;
    }


    function styleAll() {
        stylePie();

        styleTrendById(
            "trendChart"
        );

        styleTrendById(
            "aiTrendChart"
        );
    }


    function scheduleStyle(
        delay = 0
    ) {
        window.setTimeout(
            function () {
                window.requestAnimationFrame(
                    styleAll
                );
            },
            delay
        );
    }


    document.addEventListener(
        "DOMContentLoaded",
        function () {
            scheduleStyle(120);
            scheduleStyle(650);
        }
    );


    /*
     * Trend charts may only be created after
     * clicking their Show buttons.
     */
    [
        "toggleTrendChartBtn",
        "aiTrendToggle"
    ].forEach(
        function (id) {
            const button =
                document.getElementById(id);

            if (!button) {
                return;
            }

            button.addEventListener(
                "click",
                function () {
                    scheduleStyle(120);
                }
            );
        }
    );

})();
