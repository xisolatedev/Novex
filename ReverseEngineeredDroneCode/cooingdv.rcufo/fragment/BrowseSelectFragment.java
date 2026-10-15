package com.cooingdv.rcufo.fragment;

import android.os.Bundle;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.RelativeLayout;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.activity.BrowseFileActivity;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.utils.Dbug;
import com.unad.sdk.UNADFeedAd;
import com.unad.sdk.UNADFeedAdView;
import com.unad.sdk.dto.AdError;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class BrowseSelectFragment extends BaseFragment implements View.OnClickListener {
    private RelativeLayout adLayout;
    private UNADFeedAd mADManager;
    private List<UNADFeedAdView> mAdViewList = new ArrayList();
    private String whichDir = IConstants.VIEW_FRONT;

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.fragment_browse_select, viewGroup, false);
        ImageView imageView = (ImageView) viewInflate.findViewById(C3033R.id.browse_select_back);
        ImageView imageView2 = (ImageView) viewInflate.findViewById(C3033R.id.browse_select_picture);
        ImageView imageView3 = (ImageView) viewInflate.findViewById(C3033R.id.browse_select_video);
        this.adLayout = (RelativeLayout) viewInflate.findViewById(C3033R.id.browse_select_ad_layout);
        imageView.setOnClickListener(this);
        imageView2.setOnClickListener(this);
        imageView3.setOnClickListener(this);
        initBanner();
        return viewInflate;
    }

    private void initBanner() {
        if (this.mApplication.isFirstStartAPP()) {
            return;
        }
        UNADFeedAd uNADFeedAd = new UNADFeedAd(getActivity(), "Adgo-unit-3222374984", new UNADFeedAd.AdViewListener() { // from class: com.cooingdv.rcufo.fragment.BrowseSelectFragment.1
            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdClicked(UNADFeedAdView uNADFeedAdView) {
            }

            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdOpen(UNADFeedAdView uNADFeedAdView) {
            }

            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdLoaded(UNADFeedAdView uNADFeedAdView) {
                BrowseSelectFragment.this.mAdViewList.add(uNADFeedAdView);
                BrowseSelectFragment.this.adLayout.addView(uNADFeedAdView);
                uNADFeedAdView.render();
            }

            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdFailed(AdError adError) {
                Dbug.m13285e(BrowseSelectFragment.this.TAG, "onAdViewFailed.....msg:" + adError.getMessage());
            }

            @Override // com.unad.sdk.UNADFeedAd.AdViewListener
            public void onAdClose(UNADFeedAdView uNADFeedAdView) {
                BrowseSelectFragment.this.adLayout.removeView(uNADFeedAdView);
            }
        });
        this.mADManager = uNADFeedAd;
        uNADFeedAd.loadAd();
    }

    @Override // androidx.fragment.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        Bundle bundle2;
        super.onActivityCreated(bundle);
        if (getActivity() == null || (bundle2 = getBundle()) == null) {
            return;
        }
        this.whichDir = bundle2.getString(IConstants.KEY_DIR_TYPE);
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onResume() {
        super.onResume();
        UNADFeedAd uNADFeedAd = this.mADManager;
        if (uNADFeedAd != null) {
            uNADFeedAd.onResume();
        }
    }

    @Override // androidx.fragment.app.Fragment
    public void onPause() {
        super.onPause();
        UNADFeedAd uNADFeedAd = this.mADManager;
        if (uNADFeedAd != null) {
            uNADFeedAd.onPause();
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
        List<UNADFeedAdView> list = this.mAdViewList;
        if (list != null) {
            Iterator<UNADFeedAdView> it = list.iterator();
            while (it.hasNext()) {
                it.next().destroy();
            }
        }
        UNADFeedAd uNADFeedAd = this.mADManager;
        if (uNADFeedAd != null) {
            uNADFeedAd.release();
        }
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (getActivity() != null) {
            switch (view.getId()) {
                case C3033R.id.browse_select_back /* 2131296454 */:
                    getActivity().setResult(-1);
                    getActivity().onBackPressed();
                    break;
                case C3033R.id.browse_select_picture /* 2131296455 */:
                    switchFragment(0);
                    break;
                case C3033R.id.browse_select_video /* 2131296456 */:
                    switchFragment(1);
                    break;
            }
        }
    }

    private void switchFragment(int i) {
        String string;
        if (getActivity() == null) {
            return;
        }
        if (i == 0) {
            string = getString(C3033R.string.local_mode_picture);
        } else if (i == 1) {
            string = getString(C3033R.string.local_mode_video);
        } else {
            string = i != 2 ? null : getString(C3033R.string.device_mode_media);
        }
        BaseFragment browseFileFragment = (BaseFragment) getActivity().getSupportFragmentManager().findFragmentByTag(IConstants.FRAGMENT_TAG_BROWSE_FILE);
        if (browseFileFragment == null) {
            browseFileFragment = new BrowseFileFragment();
        }
        if (TextUtils.isEmpty(string)) {
            return;
        }
        Bundle bundle = new Bundle();
        bundle.putString(IConstants.KEY_FILE_NAME, string);
        bundle.putString(IConstants.KEY_DIR_TYPE, this.whichDir);
        browseFileFragment.setBundle(bundle);
        ((BrowseFileActivity) getActivity()).changeFragment(C3033R.id.browse_file_frame_layout, browseFileFragment, IConstants.FRAGMENT_TAG_BROWSE_FILE, true);
    }
}
