<?php
ob_start("ob_gzhandler");
header_remove("X-Powered-By");
header("Cache-Control: no-cache, must-revalidate, stale-if-error, no-store, max-age=0");
header("Pragma: no-cache");
header("Age: 0");
$get_version = ($_GET["action_get_version"] ?? "0") === "1";
$get_xlb = ($_GET["action_get_versioned_xlb"] ?? "0") === "1";
$fmt = $_GET["fmt"] ?? "json";
$pre = "public beta";
$v   = "2.5";
if ($get_version) {
    if ($fmt == "json") {
        header("Content-Type: application/json");
        $response = [
            "prefix" => $pre,
            "strversion" => $v
        ];
        echo json_encode($response,JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
        exit;
    } else if ($fmt == "form") {
        header("Content-Type: application/x-www-form-urlencoded");
        $response = "prefix=".$pre."&strversion=".$v;
        echo $response;
        exit;
    }
} else {
    http_response_code(416);
    exit;
}
exit;
