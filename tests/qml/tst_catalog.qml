import QtQuick
import QtTest
import "../../plasmoid/contents/ui/ProviderCatalog.js" as Catalog

TestCase {
    name: "ProviderCatalog"

    function test_referenceProviderOrder() {
        compare(Catalog.providers.length, 7)
        compare(Catalog.providers[0].provider_id, "claude")
        compare(Catalog.providers[1].provider_id, "codex")
        compare(Catalog.providers[6].provider_id, "grok")
    }

    function test_metricDefaultsAndShortLabels() {
        compare(Catalog.byId("cursor").default_metric, "total_usage")
        compare(Catalog.byId("copilot").default_metric, "credits")
        compare(Catalog.metric("codex", "spark_weekly").short_label, "SpW")
        verify(Catalog.metric("grok", "session") === null)
    }
}
