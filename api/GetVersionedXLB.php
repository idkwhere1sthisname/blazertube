<?php
ob_start("ob_gzhandler");
header_remove("X-Powered-By");
header("Cache-Control: no-cache, must-revalidate, stale-if-error, no-store, max-age=0");
header("Pragma: no-cache");
header("Age: 0");
$model = $_GET["model"] ?? "unk";
$vendor = $_GET["vendor"] ?? "UNKNOWN";
$locale = $_GET["hl"] ?? "en_US";
$fmt = $_GET["fmt"] ?? "";
$action_xlb = ($_GET["action_get_versioned_xlb"] ?? "0") === "1";
if (!$action_xlb || $fmt != "xml") {
    http_response_code(416);
    exit;
} else {
    
}
exit;
?>