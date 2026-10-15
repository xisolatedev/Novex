package com.cooingdv.rcufo.tools;

import android.app.Activity;
import android.content.Context;
import com.google.android.ump.ConsentDebugSettings;
import com.google.android.ump.ConsentForm;
import com.google.android.ump.ConsentInformation;
import com.google.android.ump.ConsentRequestParameters;
import com.google.android.ump.FormError;
import com.google.android.ump.UserMessagingPlatform;

/* JADX INFO: loaded from: classes2.dex */
public final class GoogleMobileAdsConsentManager {
    private static GoogleMobileAdsConsentManager instance;
    private final ConsentInformation consentInformation;

    public interface OnConsentGatheringCompleteListener {
        void consentGatheringComplete(FormError formError);
    }

    private GoogleMobileAdsConsentManager(Context context) {
        this.consentInformation = UserMessagingPlatform.getConsentInformation(context);
    }

    public static GoogleMobileAdsConsentManager getInstance(Context context) {
        if (instance == null) {
            instance = new GoogleMobileAdsConsentManager(context);
        }
        return instance;
    }

    public boolean canRequestAds() {
        return this.consentInformation.canRequestAds();
    }

    public boolean isPrivacyOptionsRequired() {
        return this.consentInformation.getPrivacyOptionsRequirementStatus() == ConsentInformation.PrivacyOptionsRequirementStatus.REQUIRED;
    }

    public void gatherConsent(final Activity activity, final OnConsentGatheringCompleteListener onConsentGatheringCompleteListener) {
        this.consentInformation.requestConsentInfoUpdate(activity, new ConsentRequestParameters.Builder().setConsentDebugSettings(new ConsentDebugSettings.Builder(activity).build()).build(), new ConsentInformation.OnConsentInfoUpdateSuccessListener() { // from class: com.cooingdv.rcufo.tools.GoogleMobileAdsConsentManager.1
            @Override // com.google.android.ump.ConsentInformation.OnConsentInfoUpdateSuccessListener
            public void onConsentInfoUpdateSuccess() {
                UserMessagingPlatform.loadAndShowConsentFormIfRequired(activity, new ConsentForm.OnConsentFormDismissedListener() { // from class: com.cooingdv.rcufo.tools.GoogleMobileAdsConsentManager.1.1
                    @Override // com.google.android.ump.ConsentForm.OnConsentFormDismissedListener
                    public void onConsentFormDismissed(FormError formError) {
                        onConsentGatheringCompleteListener.consentGatheringComplete(formError);
                    }
                });
            }
        }, new ConsentInformation.OnConsentInfoUpdateFailureListener() { // from class: com.cooingdv.rcufo.tools.GoogleMobileAdsConsentManager.2
            @Override // com.google.android.ump.ConsentInformation.OnConsentInfoUpdateFailureListener
            public void onConsentInfoUpdateFailure(FormError formError) {
                onConsentGatheringCompleteListener.consentGatheringComplete(formError);
            }
        });
    }

    public void showPrivacyOptionsForm(Activity activity, ConsentForm.OnConsentFormDismissedListener onConsentFormDismissedListener) {
        UserMessagingPlatform.showPrivacyOptionsForm(activity, onConsentFormDismissedListener);
    }
}
