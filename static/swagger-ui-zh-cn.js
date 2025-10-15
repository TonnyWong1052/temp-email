// 自定义 Swagger UI 语言设置为简体中文
window.onload = function() {
    // 等待 Swagger UI 完全加载
    setTimeout(function() {
        // 尝试获取 Swagger UI 实例
        if (window.ui && window.ui.specSelectors) {
            // 设置语言为简体中文
            const config = {
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout",
                deepLinking: true,
                displayRequestDuration: true,
                docExpansion: "none",
                operationsSorter: "alpha",
                filter: true,
                tryItOutEnabled: true,
                supportedSubmitMethods: ["get", "post", "put", "delete"],
                persistAuthorization: false,
                displayOperationId: false,
                showExtensions: true,
                showCommonExtensions: true,
                // 设置语言为简体中文
                lang: "zh-cn"
            };
            
            // 重新初始化 Swagger UI
            window.ui = SwaggerUIBundle({
                ...config,
                url: window.location.origin + "/openapi.json",
                dom_id: "#swagger-ui",
            });
        }
    }, 1000);
};