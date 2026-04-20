import styles from "./GcuPage.module.css";
import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { useEffect, useRef, useState } from "react";
import {
  useGetUserDetailsControlPlaneV1UserGetQuery,
  useValidateGcuControlPlaneV1GcuPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";

export default function GcuPage() {
  const { t } = useTranslation();
  const [trigger, { isLoading }] = useValidateGcuControlPlaneV1GcuPostMutation();
  const { refetch } = useGetUserDetailsControlPlaneV1UserGetQuery();

  const [hasReachedBottom, setHasReachedBottom] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasReachedBottom(true);
          observer.unobserve(entry.target);
        } else {
          setHasReachedBottom(false);
        }
      },
      {
        root: null,
        threshold: 1.0,
      },
    );

    if (bottomRef.current) {
      observer.observe(bottomRef.current);
    }

    return () => observer.disconnect();
  }, []);

  const handleAcceptGcu = async () => {
    await trigger().unwrap();
    refetch();
  };

  return (
    <div className={styles.gcuContainer}>
      <div className={styles.gcuTitle}>{t("rework.gcu.title")}</div>
      <div className={styles.gcuContent}>
        <h2>Titre de la section</h2>
        <h3>Sous titre</h3>
        Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer dapibus felis in enim posuere, quis interdum
        leo feugiat. Integer eu massa vehicula, scelerisque justo non, accumsan sem. Pellentesque eget aliquam tellus,
        suscipit efficitur libero. Donec urna libero, laoreet vel pretium eget, tempus vitae massa. Nulla eu metus
        gravida est iaculis lobortis. Praesent placerat eros at elit posuere, molestie bibendum sapien maximus. In dolor
        lorem, congue vitae eros quis, rutrum posuere tortor. Aenean id ornare eros, eget commodo eros. Nunc ut mi
        sodales, pellentesque nulla ac, accumsan mi. Phasellus fermentum vestibulum arcu, nec semper purus iaculis vel.
        Curabitur ultricies lorem vel ante mattis, ut maximus est mattis. Fusce sagittis lectus leo, vel egestas massa
        rutrum in. Morbi id porta nulla. Nulla commodo a tortor vel tincidunt. Maecenas nec massa enim. Donec imperdiet
        libero at efficitur bibendum. Nulla pulvinar mollis lacus at placerat. Lorem ipsum dolor sit amet, consectetur
        adipiscing elit. Praesent congue faucibus suscipit. Suspendisse potenti. Donec sodales in nulla vel ultrices.
        Maecenas sit amet accumsan nibh. Suspendisse at mollis purus. Curabitur sit amet tempus lacus. Nullam porta
        tincidunt eros. Mauris euismod, diam scelerisque accumsan auctor, velit elit ullamcorper purus, et luctus leo
        urna eu eros. In nec ipsum accumsan, egestas tortor ac, tempus dolor. Praesent interdum mi at dapibus interdum.
        Integer eu efficitur eros, a porttitor sapien. In et tortor at eros congue cursus. Nulla facilisi. Vestibulum
        pellentesque lorem libero, eget vulputate nisi dictum a. Phasellus ac eros fermentum, rhoncus libero sit amet,
        dictum sem. Donec iaculis eros vel blandit imperdiet. Donec et nisi ipsum. Cras enim diam, mattis at porttitor
        ut, laoreet at dolor. Morbi iaculis ipsum non velit volutpat, id tempor orci rhoncus. Cras mollis venenatis elit
        et aliquet. Nulla ut orci consequat, varius justo eget, pretium sem. Nullam ultricies felis in tincidunt
        fringilla. Nulla facilisi. Integer libero sem, interdum a tincidunt id, ornare vel urna. Ut fringilla efficitur
        orci nec posuere. Donec sapien turpis, convallis ut risus in, posuere dictum justo. Nullam iaculis fermentum
        libero, in fermentum sem rhoncus pulvinar. In aliquet pharetra luctus. Pellentesque habitant morbi tristique
        senectus et netus et malesuada fames ac turpis egestas. In mattis odio at nisl pulvinar, vitae mattis risus
        ultrices. Maecenas id sapien sed orci efficitur finibus eget sit amet mi. Morbi faucibus, magna non convallis
        lobortis, erat velit hendrerit massa, id pharetra urna leo quis nisl. Nunc laoreet nibh in ultricies bibendum.
        Donec facilisis vulputate tortor, vel laoreet tortor ultricies a. Donec ac ipsum fringilla, molestie tellus sit
        amet, posuere libero. Ut a nisi at sem tincidunt ullamcorper et ut justo. Duis accumsan sem et nisi eleifend
        laoreet et eget justo. Praesent placerat efficitur tortor. Orci varius natoque penatibus et magnis dis
        parturient montes, nascetur ridiculus mus. Pellentesque aliquam erat nec sagittis porta. Lorem ipsum dolor sit
        amet, consectetur adipiscing elit. Integer dapibus felis in enim posuere, quis interdum leo feugiat. Integer eu
        massa vehicula, scelerisque justo non, accumsan sem. Pellentesque eget aliquam tellus, suscipit efficitur
        libero. Donec urna libero, laoreet vel pretium eget, tempus vitae massa. Nulla eu metus gravida est iaculis
        lobortis. Praesent placerat eros at elit posuere, molestie bibendum sapien maximus. In dolor lorem, congue vitae
        eros quis, rutrum posuere tortor. Aenean id ornare eros, eget commodo eros. Nunc ut mi sodales, pellentesque
        nulla ac, accumsan mi. Phasellus fermentum vestibulum arcu, nec semper purus iaculis vel. Curabitur ultricies
        lorem vel ante mattis, ut maximus est mattis. Fusce sagittis lectus leo, vel egestas massa rutrum in. Morbi id
        porta nulla. Nulla commodo a tortor vel tincidunt. Maecenas nec massa enim. Donec imperdiet libero at efficitur
        bibendum. Nulla pulvinar mollis lacus at placerat. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        Praesent congue faucibus suscipit. Suspendisse potenti. Donec sodales in nulla vel ultrices. Maecenas sit amet
        accumsan nibh. Suspendisse at mollis purus. Curabitur sit amet tempus lacus. Nullam porta tincidunt eros. Mauris
        euismod, diam scelerisque accumsan auctor, velit elit ullamcorper purus, et luctus leo urna eu eros. In nec
        ipsum accumsan, egestas tortor ac, tempus dolor. Praesent interdum mi at dapibus interdum. Integer eu efficitur
        eros, a porttitor sapien. In et tortor at eros congue cursus. Nulla facilisi. Vestibulum pellentesque lorem
        libero, eget vulputate nisi dictum a. Phasellus ac eros fermentum, rhoncus libero sit amet, dictum sem. Donec
        iaculis eros vel blandit imperdiet. Donec et nisi ipsum. Cras enim diam, mattis at porttitor ut, laoreet at
        dolor. Morbi iaculis ipsum non velit volutpat, id tempor orci rhoncus. Cras mollis venenatis elit et aliquet.
        Nulla ut orci consequat, varius justo eget, pretium sem. Nullam ultricies felis in tincidunt fringilla. Nulla
        facilisi. Integer libero sem, interdum a tincidunt id, ornare vel urna. Ut fringilla efficitur orci nec posuere.
        Donec sapien turpis, convallis ut risus in, posuere dictum justo. Nullam iaculis fermentum libero, in fermentum
        sem rhoncus pulvinar. In aliquet pharetra luctus. Pellentesque habitant morbi tristique senectus et netus et
        malesuada fames ac turpis egestas. In mattis odio at nisl pulvinar, vitae mattis risus ultrices. Maecenas id
        sapien sed orci efficitur finibus eget sit amet mi. Morbi faucibus, magna non convallis lobortis, erat velit
        hendrerit massa, id pharetra urna leo quis nisl. Nunc laoreet nibh in ultricies bibendum. Donec facilisis
        vulputate tortor, vel laoreet tortor ultricies a. Donec ac ipsum fringilla, molestie tellus sit amet, posuere
        libero. Ut a nisi at sem tincidunt ullamcorper et ut justo. Duis accumsan sem et nisi eleifend laoreet et eget
        justo. Praesent placerat efficitur tortor. Orci varius natoque penatibus et magnis dis parturient montes,
        nascetur ridiculus mus. Pellentesque aliquam erat nec sagittis porta. Lorem ipsum dolor sit amet, consectetur
        adipiscing elit. Integer dapibus felis in enim posuere, quis interdum leo feugiat. Integer eu massa vehicula,
        scelerisque justo non, accumsan sem. Pellentesque eget aliquam tellus, suscipit efficitur libero. Donec urna
        libero, laoreet vel pretium eget, tempus vitae massa. Nulla eu metus gravida est iaculis lobortis. Praesent
        placerat eros at elit posuere, molestie bibendum sapien maximus. In dolor lorem, congue vitae eros quis, rutrum
        posuere tortor. Aenean id ornare eros, eget commodo eros. Nunc ut mi sodales, pellentesque nulla ac, accumsan
        mi. Phasellus fermentum vestibulum arcu, nec semper purus iaculis vel. Curabitur ultricies lorem vel ante
        mattis, ut maximus est mattis. Fusce sagittis lectus leo, vel egestas massa rutrum in. Morbi id porta nulla.
        Nulla commodo a tortor vel tincidunt. Maecenas nec massa enim. Donec imperdiet libero at efficitur bibendum.
        Nulla pulvinar mollis lacus at placerat. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Praesent
        congue faucibus suscipit. Suspendisse potenti. Donec sodales in nulla vel ultrices. Maecenas sit amet accumsan
        nibh. Suspendisse at mollis purus. Curabitur sit amet tempus lacus. Nullam porta tincidunt eros. Mauris euismod,
        diam scelerisque accumsan auctor, velit elit ullamcorper purus, et luctus leo urna eu eros. In nec ipsum
        accumsan, egestas tortor ac, tempus dolor. Praesent interdum mi at dapibus interdum. Integer eu efficitur eros,
        a porttitor sapien. In et tortor at eros congue cursus. Nulla facilisi. Vestibulum pellentesque lorem libero,
        eget vulputate nisi dictum a. Phasellus ac eros fermentum, rhoncus libero sit amet, dictum sem. Donec iaculis
        eros vel blandit imperdiet. Donec et nisi ipsum. Cras enim diam, mattis at porttitor ut, laoreet at dolor. Morbi
        iaculis ipsum non velit volutpat, id tempor orci rhoncus. Cras mollis venenatis elit et aliquet. Nulla ut orci
        consequat, varius justo eget, pretium sem. Nullam ultricies felis in tincidunt fringilla. Nulla facilisi.
        Integer libero sem, interdum a tincidunt id, ornare vel urna. Ut fringilla efficitur orci nec posuere. Donec
        sapien turpis, convallis ut risus in, posuere dictum justo. Nullam iaculis fermentum libero, in fermentum sem
        rhoncus pulvinar. In aliquet pharetra luctus. Pellentesque habitant morbi tristique senectus et netus et
        malesuada fames ac turpis egestas. In mattis odio at nisl pulvinar, vitae mattis risus ultrices. Maecenas id
        sapien sed orci efficitur finibus eget sit amet mi. Morbi faucibus, magna non convallis lobortis, erat velit
        hendrerit massa, id pharetra urna leo quis nisl. Nunc laoreet nibh in ultricies bibendum. Donec facilisis
        vulputate tortor, vel laoreet tortor ultricies a. Donec ac ipsum fringilla, molestie tellus sit amet, posuere
        libero. Ut a nisi at sem tincidunt ullamcorper et ut justo. Duis accumsan sem et nisi eleifend laoreet et eget
        justo. Praesent placerat efficitur tortor. Orci varius natoque penatibus et magnis dis parturient montes,
        nascetur ridiculus mus. Pellentesque aliquam erat nec sagittis porta.
        <div ref={bottomRef} />
      </div>
      <div className={styles.gcuActions}>
        <span className={styles.gcuLockInformation}>{t("rework.gcu.lockInformation")}</span>
        <Button
          color={"primary"}
          variant={"filled"}
          size={"medium"}
          disabled={!hasReachedBottom || isLoading}
          onClick={handleAcceptGcu}
        >
          Valider
        </Button>
      </div>
    </div>
  );
}
