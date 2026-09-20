// Shows only the settings used by the selected quest type, with a short explanation of the type, and hides the
// measure field when the type only supports one way of counting.
django.jQuery(function ($) {
    const typeSelect = $("#id_type");
    if (!typeSelect.length) {
        return;
    }
    const helps = typeSelect.data("type-help") || {};
    const goalLabels = typeSelect.data("goal-labels") || {};
    const measures = typeSelect.data("measures") || {};
    const goalLabel = $("label[for=id_target]");
    const measureSelect = $("#id_measure");
    const helpBox = $('<div class="help eventpass-type-help"></div>');
    typeSelect.closest(".form-row").find(".flex-container").first().after(helpBox);

    function update() {
        const selected = typeSelect.val();
        const sections = new Set();
        $(".eventpass-param").each(function () {
            const types = String($(this).data("quest-types") || "").split(",");
            $(this).closest(".form-row").toggle(types.includes(selected));
            sections.add($(this).closest("fieldset")[0]);
        });
        // A section left with nothing to show goes away entirely, header included. Whether a row is wanted is read
        // from the type it belongs to, not from its CSS: a collapsed section keeps its rows "displayed".
        sections.forEach(function (section) {
            const wanted = $(section)
                .find(".eventpass-param")
                .filter(function () {
                    return String($(this).data("quest-types") || "").split(",").includes(selected);
                });
            const plainRows = $(section)
                .find(".form-row")
                .filter(function () {
                    return $(this).find(".eventpass-param").length === 0;
                });
            $(section).toggle(wanted.length > 0 || plainRows.length > 0);
        });
        const help = helps[selected] || "";
        helpBox.text(help);
        helpBox.css("color", help.indexOf("⚠") === -1 ? "" : "#b32d2e");
        if (goalLabel.length) {
            goalLabel.text((goalLabels[selected] || "Goal") + ":");
        }
        const allowed = measures[selected] || ["count"];
        if (measureSelect.length) {
            measureSelect.closest(".form-row").toggle(allowed.length > 1);
            measureSelect.find("option").each(function () {
                const value = $(this).attr("value");
                $(this).prop("disabled", value !== "" && allowed.indexOf(value) === -1);
            });
            if (allowed.indexOf(measureSelect.val()) === -1) {
                measureSelect.val(allowed[0]);
            }
        }
    }

    typeSelect.on("change", update);
    update();
});
