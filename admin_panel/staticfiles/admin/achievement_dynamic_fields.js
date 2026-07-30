django.jQuery(function ($) {
    function toggleFields() {
        const selectedType = $("#id_type").val();
        $(".extra-param-field").each(function () {
            const row = $(this).closest(".form-row");
            const relevantTypes = $(this).data("achievement-types").split(",");
            row.toggle(relevantTypes.includes(selectedType));
        });
    }

    $("#id_type").on("change", toggleFields);
    toggleFields();
});