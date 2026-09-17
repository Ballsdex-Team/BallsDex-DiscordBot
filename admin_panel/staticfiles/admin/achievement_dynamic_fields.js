// Shows only the settings used by the selected achievement type, with a short explanation of the type.
django.jQuery(function ($) {
    const typeSelect = $("#id_type");
    if (!typeSelect.length) {
        return;
    }
    const helps = typeSelect.data("type-help") || {};
    const goalLabels = typeSelect.data("goal-labels") || {};
    const goalLabel = $("label[for=id_target_value]");
    const helpBox = $('<div class="help achievement-type-help"></div>');
    typeSelect.closest(".form-row").find(".flex-container").first().after(helpBox);

    function update() {
        const selected = typeSelect.val();
        $(".achievement-param").each(function () {
            const types = String($(this).data("achievement-types") || "").split(",");
            $(this).closest(".form-row").toggle(types.includes(selected));
        });
        helpBox.text(helps[selected] || "");
        if (goalLabel.length) {
            goalLabel.text((goalLabels[selected] || "Goal") + ":");
        }
    }

    typeSelect.on("change", update);
    update();
});
