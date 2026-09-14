// should be hulu compatible(?)
var flush = null;

function getInfo() {
    return {
        device: {
            chipset: vod.deviceChipset(),
            firmware: vod.deviceFirmware(),
            width: vod.screenWidth(),
            height: vod.screenHeight(),
            whcombo: vod.screenResolution()
        },
        conn: {
            strength: vod.connectionStrength(),
            type: vod.connectionType()
        },
        app: {
            jsb: vod.jsbVersion(),
            distributedVideoRestricted: vod.isDistributedVideoRestricted()
        },
        user: {
            token: vod.token(),
            consumerdata: vod.consumerData(),
            parental: vod.isParentalControlActivated(),
            ip: vod.clientIP(),
            languagecode: vod.languageCode(),
            new3DS: vod.n3ds_IsNew3DS()
        },
        FlexView: {
            ViewFlags: {
                SupportStencil: vod.FlexView_ViewFlags_SupportStencil,
                ScrollingX: vod.FlexView_ViewFlags_ScrollingX,
                ScrollingY: vod.FlexView_ViewFlags_ScrollingY,
                None: vod.FlexView_ViewFlags_None,
                Hidden: vod.FlexView_ViewFlags_Hidden,
                Default: vod.FlexView_ViewFlags_Default,
                NoScrollingClampX: vod.FlexView_ViewFlags_NoScrollingClampX,
                NoScrollingClampY: vod.FlexView_ViewFlags_NoScrollingClampY,
                JSB: vod.FlexView_ViewFlags_JSB,
                TouchScrollingX: vod.FlexView_ViewFlags_TouchScrollingX,
                TouchScrollingY: vod.FlexView_ViewFlags_TouchScrollingY,
                InitWithPhysicalPixels: vod.FlexView_ViewFlags_InitWithPhysicalPixels,
                InitScrollWithPhysicalPixels: vod.FlexView_ViewFlags_InitScrollWithPhysicalPixels,
                Hint: {
                    RenderQualityColorLow: vod.FlexView_ViewFlags_Hint_RenderQualityColorLow,
                    RenderQualityColorHigh: vod.FlexView_ViewFlags_Hint_RenderQualityColorHigh,
                    RenderQualityAlphaLow: vod.FlexView_ViewFlags_Hint_RenderQualityAlphaLow,
                    RenderQualityAlphaHigh: vod.FlexView_ViewFlags_Hint_RenderQualityAlphaHigh,
                }
            },
            InputMask: {
                MouseAll: vod.FlexView_InputMask_MouseAll,
                All: vod.FlexView_InputMask_All,
                None: vod.FlexView_InputMask_None,
                KeyUp: vod.FlexView_InputMask_KeyUp,
                KeyDown: vod.FlexView_InputMask_KeyDown,
                KeyAll: vod.FlexView_InputMask_KeyAll,
                MouseMove: vod.FlexView_InputMask_MouseMove,
                MouseTrigger: vod.FlexView_InputMask_MouseTrigger,
                MouseRelease: vod.FlexView_InputMask_MouseRelease,
                UserScrollLink: vod.FlexView_InputMask_UserScrollLink,
            }
        },
        environment: {
            mvId: vod.getMiiverseLink()
        }
    }
}
function showSpinnerWithoutBackground(x,y) {
    if (x == null) {
        x = 15;
    }
    if (y == null) {
        y = 15
    }
    vod.showSpinnerWithoutBackground(10,{x:x,y:y});
    return undefined;
}
function hideSpinnerWithoutBackground() {
    vod.hideSpinner(0)
    return undefined;
}
function showTopSpinner() {
    vod.showProgressSpinner(true);
    return undefined;
}
function hideTopSpinner() {
    vod.showProgressSpinner(false);
    return undefined;
}

function setTime(launcherUrl,retryCount,maxRetries,appName) {
    retryCount = retryCount ?? 0;
    maxRetries = maxRetries ?? 3;
    appName = appName ?? "APP_NAME_99";
    function retryCheck() {
        retryCount++;
        if (retryCount === maxRetries) {
            console.log("get time failed.")
            window.open("http://embedded.ctr/error.html?error="+encodeURIComponent(appName),"_self");
            return;
        }
        loadFileToElement();
    }
    function loadFileToElement() {
        var xmlHTTP = new XMLHttpRequest();
        xmlHTTP.onreadystatechange = function () {
            if (xmlHTTP.readyState!==4) {
                retryCheck();
                return;
            }
            if (xmlHTTP.status<200 || xmlHTTP.status>=300) {
                retryCheck();
                return;
            }
            try {
                var dateHeader = xmlHTTP.getResponseHeader("date");
                var actualTimeFromJSON = new Date(dateHeader).getTime();
                if (isNaN(actualTimeFromJSON)) {
                    retryCheck();
                    return;
                }
                console.log("New timestamp (actualTimeFromJSON): "+actualTimeFromJSON);
                vod.setTime(actualTimeFromJSON);
            } catch (e) {
                retryCheck();
            }
        };
        try {
            xmlHTTP.open("GET",launcherUrl,true);
            xmlHTTP.send();
        } catch (e) {
            retryCheck();
        }
    }
    loadFileToElement();
}

function startFlushLoop() {
    if (flush !== null) {
        return;
    }
    flush = setInterval(()=>{
        vod.flushMemory();
    },10000);
}

function stopFlushLoop(loopOverride) {
    var loop = loopOverride ?? flush;
    if (loop !== null) {
        clearInterval(loop);
    };
    if (loopOverride === null) {
        flush = null;
    };
}
