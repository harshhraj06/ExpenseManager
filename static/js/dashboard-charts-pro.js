(() => {
    "use strict";


    const PIE_COLORS = [
        "#7b899c",
        "#9b8371",
        "#788f86",
        "#8b7d94",
        "#9a9074",
        "#788893",
        "#927d7d",
        "#728593"
    ];


    function money(value) {

        return "₹" +
            Number(value || 0)
            .toLocaleString(
                "en-IN",
                {
                    maximumFractionDigits: 2
                }
            );
    }


    function getChart(id) {

        if (
            !window.Chart
            || !Chart.getChart
        ) {
            return null;
        }

        return Chart.getChart(id);
    }


    /* ==================================================
       PIE
       ================================================== */

    function stylePie() {

        const chart =
            getChart(
                "expenseChart"
            );

        if (!chart) {
            return false;
        }


        const dataset =
            chart.data.datasets[0];

        if (!dataset) {
            return false;
        }


        dataset.backgroundColor =
            chart.data.labels.map(
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


        chart.options.layout = {
            padding: 8
        };


        chart.options.plugins =
            chart.options.plugins
            || {};


        chart.options.plugins.legend = {

            position:
                "right",

            labels: {

                color:
                    "#98a3ae",

                usePointStyle:
                    true,

                pointStyle:
                    "circle",

                boxWidth:
                    8,

                boxHeight:
                    8,

                padding:
                    14,

                font: {
                    size: 11,
                    weight: "500"
                }
            }
        };


        chart.options.plugins.tooltip = {

            backgroundColor:
                "#171d24",

            titleColor:
                "#eef1f4",

            bodyColor:
                "#aeb8c2",

            borderColor:
                "rgba(255,255,255,.10)",

            borderWidth:
                1,

            padding:
                11,

            displayColors:
                true,

            boxWidth:
                8,

            boxHeight:
                8,

            cornerRadius:
                9,

            callbacks: {

                label(context) {

                    const value =
                        Number(
                            context.raw || 0
                        );

                    const values =
                        context.dataset.data
                        || [];

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


        chart.update();

        return true;
    }


    /* ==================================================
       TREND
       ================================================== */

    function styleTrendById(
        id
    ) {

        const chart =
            getChart(id);

        if (!chart) {
            return false;
        }


        const colors = [
            "#789681",
            "#a27f7d"
        ];


        chart.data.datasets
        .forEach(
            (dataset, index) => {

                dataset.borderColor =
                    colors[
                        index %
                        colors.length
                    ];

                dataset.backgroundColor =
                    "transparent";

                dataset.borderWidth =
                    2;

                dataset.pointBackgroundColor =
                    colors[
                        index %
                        colors.length
                    ];

                dataset.pointBorderColor =
                    "#10151b";

                dataset.pointBorderWidth =
                    2;

                dataset.pointRadius =
                    3;

                dataset.pointHoverRadius =
                    5;

                dataset.tension =
                    .35;

                dataset.fill =
                    false;
            }
        );


        chart.options.interaction = {
            intersect: false,
            mode: "index"
        };


        chart.options.plugins =
            chart.options.plugins
            || {};


        chart.options.plugins.legend = {

            position: "top",

            align: "end",

            labels: {

                color:
                    "#8995a0",

                usePointStyle:
                    true,

                pointStyle:
                    "circle",

                boxWidth:
                    8,

                boxHeight:
                    8,

                padding:
                    14,

                font: {
                    size: 11
                }
            }
        };


        chart.options.plugins.tooltip = {

            backgroundColor:
                "#171d24",

            titleColor:
                "#eef1f4",

            bodyColor:
                "#abb5bf",

            borderColor:
                "rgba(255,255,255,.10)",

            borderWidth:
                1,

            padding:
                11,

            cornerRadius:
                9,

            callbacks: {

                label(context) {

                    return (
                        " " +
                        context.dataset.label +
                        ": " +
                        money(
                            context.raw
                        )
                    );
                }
            }
        };


        if (
            chart.options.scales
        ) {

            ["x", "y"]
            .forEach((axis) => {

                if (
                    !chart.options.scales[
                        axis
                    ]
                ) {
                    return;
                }


                const scale =
                    chart.options.scales[
                        axis
                    ];


                scale.border = {
                    display: false
                };


                scale.grid = {

                    color:
                        axis === "y"
                            ? "rgba(255,255,255,.055)"
                            : "rgba(255,255,255,.025)",

                    drawTicks:
                        false
                };


                scale.ticks =
                    scale.ticks
                    || {};


                scale.ticks.color =
                    "#687480";

                scale.ticks.padding =
                    9;

                scale.ticks.font = {
                    size: 10
                };


                if (
                    axis === "y"
                ) {

                    scale.ticks.callback =
                        function(value) {

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
                                    )
                                    .toFixed(1) +
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
                                    )
                                    .toFixed(0) +
                                    "k"
                                );
                            }

                            return (
                                "₹" +
                                number
                            );
                        };
                }

            });
        }


        chart.update();

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


    document.addEventListener(
        "DOMContentLoaded",
        () => {

            setTimeout(
                styleAll,
                100
            );

            setTimeout(
                styleAll,
                500
            );

        }
    );


    /*
     * Trend charts may be created only
     * after their Show button is clicked.
     */

    [
        "toggleTrendChartBtn",
        "aiTrendToggle"
    ]
    .forEach((id) => {

        const button =
            document.getElementById(id);

        if (!button) {
            return;
        }


        button.addEventListener(
            "click",
            () => {

                setTimeout(
                    styleAll,
                    80
                );

                setTimeout(
                    styleAll,
                    300
                );

            }
        );

    });

})();
