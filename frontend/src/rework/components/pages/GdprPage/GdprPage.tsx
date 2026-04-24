import styles from "./GdprPage.module.css";
import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export default function GdprPage() {
  const { t } = useTranslation();

  return (
    <div className={styles.gdprContainer}>
      <div className={styles.gdprTitle}>{t("rework.gcu.title")}</div>
      <div className={styles.gdprContent}>
        <div className={styles.gdprSection}>Last update: April 2026</div>
        <div className={styles.gdprSection}>
          <h2>Privacy Notice</h2>
          <div>
            The protection of your personal data is of high importance to THALES, therefore THALES takes all reasonable
            care to ensure that your personal data is processed safely.
          </div>
          <div>What personal data do we collect from you?</div>
          <div>· User login credentials</div>
          <div>· Service usage metadata</div>
          <div>
            · User content, including user’s prompts and more generally all content uploaded by user that qualify as
            personal data
          </div>
          <div>
            · PRISM website log data when you use PRISM: including your IP address, the date and time of your access,
            how you used PRISM.
          </div>
          <div>
            · Information you voluntarily provide in contact forms, including (first and last) name, email address.
          </div>
        </div>
        <div className={styles.gdprSection}>
          <h2>What is your data used for?</h2>
          <div>Your data is used for the following purposes: </div>
          <div>· Users access management</div>
          <div>· Continous service improvement</div>
          <div>· Security and compliance monitoring</div>
        </div>
        <div className={styles.gdprSection}>
          <h2>What is the legal basis for the processing of your personal data?</h2>
          <div>
            In order to carry out the processing activities specified therein, THALES relies on its legitimate interest,
            which consists of ensuring a suitable working environment by providing, amongst other thing, IT applications
            at the state of the art as well as ensuring the continuity of its business activity
          </div>
        </div>
        <div className={styles.gdprSection}>
          <h2>How long do we keep your personal data?</h2>
          <div>12 months following the cessation of the relation between Thales and the User.</div>
        </div>
        <div className={styles.gdprSection}>
          <h2>Who are the recipients of your personal data?</h2>
          <div>
            In the context of such processing, the recipients of all or part of your personal data will be the personnel
            of THALES and entities of its group in charge to operating the IT infrastructures, as well as, when
            applicable, some personnel of third parties, in charge of the hosting and maintenance of such
            infrastructure, all such recipients being located within the European Economic Area (EEA) and in the
            countries referred to below.
          </div>
        </div>
        <div className={styles.gdprSection}>
          <h2>Is your personal data transferred out of the European Economic Area?</h2>
          <div>
            The sharing of your personal data with certain recipients may imply transfers of your data out of the
            European Economic Area (EEA) in the countries where the entities of the THALES group operate [included in
            the
            <a href={"https://www.thalesgroup.com/en/global/group/about-us/thales-worldwide"}>Thales address book</a>].
            THALES pays particular attention to the protection of your personal data. When such transfer is made by a
            Thales entity established in a country in the EEA or in the UK to a Thales entity established in a third
            country outside the EEA or the UK that has not been recognized as providing an adequate level of protection
            by an adequacy decision of the European Commission or the UK, Thales relies on its Binding Corporate Rules.
            Thanks to the Thales BCR, wherever your personal data is processed within the Thales Group, it benefits from
            the same standard of protection. You can access the Thales BCR by clicking
            <a
              href={
                "https://chorus2.corp.thales/group/guest/search?p_p_id=SearchResultPortlet_WAR_searchresultportlet100SNAPSHOT&q=BCR"
              }
            >
              here
            </a>
          </div>
        </div>
        <div className={styles.gdprSection}>
          <h2>What are your rights related to your personal data?</h2>
          <div>
            Please note that you have the right to access your personal data and to request that your personal data be
            rectified or deleted. You are also entitled to request restriction of the processing of your personal data.
            In addition, you have the right to ask for receiving, in a structured and standard format, your personal
            data that you provided to THALES and which THALES processes by automated means.
          </div>
          <div>
            In case of any request or complaint, you can contact PRISM support team by sending an email to the following
            address : <a href="mailto:prism-ai-hub@thalesgroup.com">prism-ai-hub@thalesgroup.com</a>. You can also
            contact Thales Group Data Protection Officer by sending an email to the following email address:
            <a href="mailto:dataprotection@thalesgroup.com">dataprotection@thalesgroup.com</a>. In any case, you also
            have the right to lodge a complaint with the competent data protection authority.
          </div>
        </div>
      </div>
      <div className={styles.gdprActions}>
        <Link to={"/"}>
          <Button color={"primary"} variant={"filled"} size={"medium"}>
            {t("rework.gcu.backToApp")}
          </Button>
        </Link>
      </div>
    </div>
  );
}
