plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "top.hypixice.poros"
    compileSdk = 35

    defaultConfig {
        applicationId = "top.hypixice.poros"
        minSdk = 26
        targetSdk = 35
        versionCode = (findProperty("versionCode") as String?)?.toIntOrNull() ?: 1
        versionName = (findProperty("versionName") as String?) ?: "0.1.6"
    }

    signingConfigs {
        create("poros") {
            // rootProject, not file(): inside the app module "keystore/..."
            // would resolve to android/app/keystore, which does not exist.
            storeFile = rootProject.file("keystore/poros-test.jks")
            storePassword = "poros123"
            keyAlias = "poros"
            keyPassword = "poros123"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("poros")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("poros")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
        viewBinding = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.kotlinx.coroutines.android)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    debugImplementation(libs.androidx.ui.tooling)

    implementation(libs.okhttp)
    implementation(libs.webrtc.android)
    implementation(libs.socketio.client) {
        exclude(group = "org.json", module = "json")
    }

    // Camera capture: CameraX for resolution discovery, the streaming engine and
    // its RTSP server for the hardware encode + publish pipeline.
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.rootencoder)
    implementation(libs.rtsp.server)
}
