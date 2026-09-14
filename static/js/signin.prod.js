function checkIsSignedIn() {
    var ival = setInterval(function() {
        var xmlHTTP = new XMLHttpRequest();
        xmlHTTP.open("POST","/vendor_signin/poll",true);
        xmlHTTP.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
        xmlHTTP.onreadystatechange = function() {
            if (xmlHTTP.readyState == 4) {
                if (xmlHTTP.status >= 200 && xmlHTTP.status <= 299) {
                    try {
                        var data = JSON.parse(xmlHTTP.responseText);
                        if (data.status === "success") {
                            clearInterval(ival);
                            console.log("New user (actualUserFromJSON): "+"user")
                            var commonForm = document.createElement("form");
                            commonForm.method = "POST";
                            commonForm.action = "/vendor_signin?action_success=1";
                            var deviceCode = document.createElement("input");
                            deviceCode.type = "hidden";
                            deviceCode.name = "device_code";
                            deviceCode.value = ACT_DCD;
                            commonForm.appendChild(deviceCode);
                            document.body.appendChild(commonForm);
                            commonForm.submit();
                        } else if (data.status === "error" || data.status === "reload") {
                            clearInterval(ival);
                            window.location.reload();
                        }
                    } catch (e) {
                        console.log("Error: "+e);
                    }
                } else {
                    console.log("Error: "+xmlHTTP.status);
                }
            }
        };
        var payload = "device_code="+encodeURIComponent(ACT_DCD);
        xmlHTTP.send(payload);
    },5000);
}
