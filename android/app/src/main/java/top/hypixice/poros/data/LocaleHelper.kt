package top.hypixice.poros.data

import android.content.Context
import android.content.res.Configuration
import android.os.LocaleList
import java.util.Locale

/**
 * Applies the language chosen in Settings to a Context's resources.
 *
 * minSdk is 26 and the app does not use AppCompat, so the (API 33+)
 * LocaleManager is not an option. Wrapping the base context instead localises
 * every string resource - the Activity and the Service both go through it.
 */
object LocaleHelper {
    private val SUPPORTED = setOf("en", "zh", "vi")

    fun wrap(base: Context): Context {
        val code = Prefs(base).language.lowercase(Locale.ROOT)
        val tag = if (code in SUPPORTED) code else "en"
        val locale = Locale.forLanguageTag(tag)
        val config = Configuration(base.resources.configuration)
        config.setLocales(LocaleList(locale))
        return base.createConfigurationContext(config)
    }
}
