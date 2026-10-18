plugins {
    id("com.android.application")
}

android {
    namespace = "com.earshot.companion"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.earshot.companion"
        minSdk = 33          // Android 13: runtime notification permission exists
        targetSdk = 37       // Android 17, what the Pixel 10 Pro runs
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    // WebSocket server (phone hosts the bridge) and client (relay through a laptop).
    implementation("org.java-websocket:Java-WebSocket:1.6.0")
}
